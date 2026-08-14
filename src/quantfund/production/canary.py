"""Controlled canary mode — small explicit limits; no automatic order submit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quantfund.brokers.base import BrokerOrderRequest
from quantfund.production.controls import ControlDecision, ProductionTradingControls


@dataclass(frozen=True)
class CanaryLimits:
    max_order_value: float
    max_position_value: float
    max_daily_loss: float
    max_orders: int

    def __post_init__(self) -> None:
        if self.max_order_value <= 0:
            raise ValueError("canary max_order_value must be > 0")
        if self.max_position_value <= 0:
            raise ValueError("canary max_position_value must be > 0")
        if self.max_daily_loss <= 0:
            raise ValueError("canary max_daily_loss must be > 0")
        if self.max_orders <= 0:
            raise ValueError("canary max_orders must be > 0")


@dataclass
class CanaryReadiness:
    ready: bool
    blockers: list[str]
    limits: dict[str, float | int]
    auto_submit: bool = False  # always False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "blockers": list(self.blockers),
            "limits": dict(self.limits),
            "auto_submit": self.auto_submit,
            "note": "Canary readiness ≠ order submission.",
        }


def evaluate_canary_readiness(
    *,
    limits: CanaryLimits,
    controls: ProductionTradingControls,
    activation_allowed: bool,
    preflight_ok: bool,
    reconciliation_clean: bool,
) -> CanaryReadiness:
    blockers: list[str] = []
    if not activation_allowed:
        blockers.append("activation_gates_not_satisfied")
    if not preflight_ok:
        blockers.append("preflight_not_ok")
    if not reconciliation_clean:
        blockers.append("reconciliation_not_clean")
    if controls.kill_switch.is_triggered:
        blockers.append("kill_switch_triggered")
    if controls.global_trading_disabled:
        blockers.append("global_trading_disabled")
    # canary limits must be stricter than or equal to production ceilings
    if limits.max_order_value > controls.limits.max_order_value:
        blockers.append("canary_max_order_value_exceeds_production")
    if limits.max_daily_loss > controls.limits.max_daily_loss:
        blockers.append("canary_max_daily_loss_exceeds_production")
    if limits.max_orders > controls.limits.max_orders:
        blockers.append("canary_max_orders_exceeds_production")
    return CanaryReadiness(
        ready=len(blockers) == 0,
        blockers=blockers,
        limits={
            "max_order_value": limits.max_order_value,
            "max_position_value": limits.max_position_value,
            "max_daily_loss": limits.max_daily_loss,
            "max_orders": limits.max_orders,
        },
        auto_submit=False,
    )


def canary_check_order(
    request: BrokerOrderRequest,
    *,
    ref_price: float,
    limits: CanaryLimits,
    controls: ProductionTradingControls,
) -> ControlDecision:
    """Canary never bypasses production controls."""
    base = controls.check_new_order(request, ref_price=ref_price)
    if not base.allowed:
        return base
    value = float(request.quantity) * ref_price
    if value > limits.max_order_value + 1e-9:
        return ControlDecision(False, "canary_max_order_value")
    if controls.order_count >= limits.max_orders:
        return ControlDecision(False, "canary_max_orders")
    pos = controls.positions.get(request.symbol, 0.0) + float(request.quantity)
    if pos * ref_price > limits.max_position_value + 1e-9:
        return ControlDecision(False, "canary_max_position_value")
    return ControlDecision(True, None)

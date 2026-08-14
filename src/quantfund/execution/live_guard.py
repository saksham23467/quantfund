"""LiveExecutionGuard — fail-closed checks before every broker order send."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.brokers.base import BrokerOrderRequest
from quantfund.brokers.intent_store import ExecutionIntentStore
from quantfund.execution.broker_adapter import BrokerHealth
from quantfund.execution.modes import QuantFundExecutionMode
from quantfund.paper.kill_switch import KillSwitch


@dataclass(frozen=True)
class LiveGuardLimits:
    max_order_quantity: float = 100.0
    max_order_notional: float = 50_000.0
    max_daily_orders: int = 20
    max_daily_loss: float = 5_000.0
    max_turnover: float = 200_000.0
    max_position_quantity: float = 500.0
    allowed_instruments: frozenset[str] = field(default_factory=frozenset)
    # empty allowed_instruments ⇒ allow any (tests may set explicitly)


@dataclass
class LiveGuardDecision:
    allowed: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason}


@dataclass
class LiveExecutionGuard:
    """Broker-side execution guard. RiskEngine cannot be bypassed via adapter."""

    mode: QuantFundExecutionMode
    kill_switch: KillSwitch
    intent_store: ExecutionIntentStore
    limits: LiveGuardLimits
    day_start_equity: float | None = None
    current_equity: float | None = None
    order_count: int = 0
    turnover: float = 0.0
    positions: dict[str, float] = field(default_factory=dict)
    session_valid: bool = True

    def check(
        self,
        request: BrokerOrderRequest,
        *,
        health: BrokerHealth,
        ref_price: float,
    ) -> LiveGuardDecision:
        if self.mode not in {
            QuantFundExecutionMode.BROKER_SANDBOX,
            QuantFundExecutionMode.BROKER_LIVE,
        }:
            return LiveGuardDecision(False, "execution_mode_not_broker")
        if self.mode == QuantFundExecutionMode.OFF:
            return LiveGuardDecision(False, "execution_mode_off")
        if not health.connected:
            return LiveGuardDecision(False, "broker_unhealthy")
        if self.kill_switch.is_triggered:
            return LiveGuardDecision(False, "kill_switch")
        if not self.session_valid:
            return LiveGuardDecision(False, "session_invalid")
        if self.intent_store.has_broker_order(request.execution_intent_id):
            return LiveGuardDecision(False, "duplicate_intent")
        if self.limits.allowed_instruments and (
            request.instrument_id not in self.limits.allowed_instruments
            and request.symbol.upper()
            not in {s.upper() for s in self.limits.allowed_instruments}
        ):
            return LiveGuardDecision(False, "instrument_not_allowed")
        if request.quantity > self.limits.max_order_quantity + 1e-9:
            return LiveGuardDecision(False, "quantity_limit")
        if ref_price <= 0:
            return LiveGuardDecision(False, "invalid_ref_price")
        notional = float(request.quantity) * ref_price
        if notional > self.limits.max_order_notional + 1e-9:
            return LiveGuardDecision(False, "notional_limit")
        if self.order_count >= self.limits.max_daily_orders:
            return LiveGuardDecision(False, "daily_order_count")
        if self.turnover + notional > self.limits.max_turnover + 1e-9:
            return LiveGuardDecision(False, "turnover_limit")
        if (
            self.day_start_equity is not None
            and self.current_equity is not None
            and (self.day_start_equity - self.current_equity)
            > self.limits.max_daily_loss + 1e-9
        ):
            return LiveGuardDecision(False, "daily_loss_limit")
        pos = self.positions.get(request.symbol, 0.0)
        # projected long qty after buy
        projected = pos + float(request.quantity)
        if projected > self.limits.max_position_quantity + 1e-9:
            return LiveGuardDecision(False, "position_limit")
        return LiveGuardDecision(True, None)

    def record_accepted(self, request: BrokerOrderRequest, *, ref_price: float) -> None:
        self.order_count += 1
        self.turnover += float(request.quantity) * ref_price

"""Layered production trading controls + kill switch hardening."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.brokers.base import BrokerOrderRequest
from quantfund.paper.kill_switch import KillSwitch


@dataclass
class ProductionControlLimits:
    max_order_quantity: float = 100.0
    max_order_value: float = 25_000.0
    max_daily_loss: float = 5_000.0
    max_turnover: float = 100_000.0
    max_orders: int = 20
    max_open_orders: int = 5
    max_position: float = 200.0
    max_exposure: float = 50_000.0
    disabled_symbols: frozenset[str] = field(default_factory=frozenset)


@dataclass
class ControlDecision:
    allowed: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason}


@dataclass
class ProductionTradingControls:
    """Independent disable switches + hard ceilings. Fail closed; never silent."""

    kill_switch: KillSwitch
    limits: ProductionControlLimits
    global_trading_disabled: bool = False
    strategy_disabled: bool = False
    broker_disabled: bool = False
    order_count: int = 0
    open_orders: int = 0
    turnover: float = 0.0
    day_start_equity: float | None = None
    current_equity: float | None = None
    positions: dict[str, float] = field(default_factory=dict)

    def check_new_order(
        self,
        request: BrokerOrderRequest,
        *,
        ref_price: float,
    ) -> ControlDecision:
        if self.global_trading_disabled:
            return ControlDecision(False, "global_trading_disabled")
        if self.strategy_disabled:
            return ControlDecision(False, "strategy_disabled")
        if self.broker_disabled:
            return ControlDecision(False, "broker_disabled")
        if self.kill_switch.is_triggered:
            return ControlDecision(False, "kill_switch")
        sym = request.symbol.upper()
        if sym in {s.upper() for s in self.limits.disabled_symbols}:
            return ControlDecision(False, "symbol_disabled")
        if request.quantity > self.limits.max_order_quantity + 1e-9:
            return ControlDecision(False, "maximum_order_quantity")
        if ref_price <= 0:
            return ControlDecision(False, "invalid_ref_price")
        value = float(request.quantity) * ref_price
        if value > self.limits.max_order_value + 1e-9:
            return ControlDecision(False, "maximum_order_value")
        if self.order_count >= self.limits.max_orders:
            return ControlDecision(False, "maximum_number_of_orders")
        if self.open_orders >= self.limits.max_open_orders:
            return ControlDecision(False, "maximum_open_orders")
        if self.turnover + value > self.limits.max_turnover + 1e-9:
            return ControlDecision(False, "maximum_turnover")
        if (
            self.day_start_equity is not None
            and self.current_equity is not None
            and (self.day_start_equity - self.current_equity)
            > self.limits.max_daily_loss + 1e-9
        ):
            return ControlDecision(False, "maximum_daily_loss")
        pos = self.positions.get(request.symbol, 0.0) + float(request.quantity)
        if pos > self.limits.max_position + 1e-9:
            return ControlDecision(False, "maximum_position")
        exposure = abs(pos) * ref_price
        if exposure > self.limits.max_exposure + 1e-9:
            return ControlDecision(False, "maximum_exposure")
        return ControlDecision(True, None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_trading_disabled": self.global_trading_disabled,
            "strategy_disabled": self.strategy_disabled,
            "broker_disabled": self.broker_disabled,
            "kill_switch": self.kill_switch.to_dict(),
            "order_count": self.order_count,
            "open_orders": self.open_orders,
            "limits": {
                "max_order_quantity": self.limits.max_order_quantity,
                "max_order_value": self.limits.max_order_value,
                "max_daily_loss": self.limits.max_daily_loss,
                "max_turnover": self.limits.max_turnover,
                "max_orders": self.limits.max_orders,
                "max_open_orders": self.limits.max_open_orders,
                "max_position": self.limits.max_position,
                "max_exposure": self.limits.max_exposure,
            },
        }

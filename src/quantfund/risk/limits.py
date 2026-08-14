"""Minimal independent risk checks for Milestone 1.

Supports:
- maximum order value
- maximum position value
- maximum total exposure

Designed for later extension: daily loss, max drawdown, kill switch, etc.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantfund.trading.models import Order, OrderSide, OrderStatus


@dataclass(frozen=True)
class RiskConfig:
    """Configurable hard limits. Strategy cannot override these."""

    max_order_value: float = 100_000.0
    max_position_value: float = 100_000.0
    max_total_exposure: float = 100_000.0
    # Placeholders for future phases (not enforced in M1):
    max_daily_loss: float | None = None
    max_drawdown: float | None = None
    kill_switch: bool = False


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    order: Order
    reason: str | None = None


class RiskEngine:
    """Independent risk filter applied after strategy order generation."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def check_order(
        self,
        order: Order,
        *,
        ref_price: float,
        current_position_qty: float,
        current_exposure: float,
    ) -> RiskDecision:
        """Accept, reject, or clip an order. Strategies cannot bypass this."""
        if self.config.kill_switch:
            rejected = order.model_copy(
                update={"status": OrderStatus.REJECTED, "reject_reason": "kill_switch"}
            )
            return RiskDecision(False, rejected, "kill_switch")

        if ref_price <= 0:
            rejected = order.model_copy(
                update={"status": OrderStatus.REJECTED, "reject_reason": "invalid_ref_price"}
            )
            return RiskDecision(False, rejected, "invalid_ref_price")

        order_value = order.quantity * ref_price
        if order_value > self.config.max_order_value + 1e-9:
            rejected = order.model_copy(
                update={
                    "status": OrderStatus.REJECTED,
                    "reject_reason": "max_order_value",
                }
            )
            return RiskDecision(False, rejected, "max_order_value")

        if order.side == OrderSide.BUY:
            new_qty = current_position_qty + order.quantity
            new_position_value = new_qty * ref_price
            new_exposure = current_exposure - (current_position_qty * ref_price) + new_position_value
        else:
            # M1: no shorts — reject sells larger than position.
            if order.quantity > current_position_qty + 1e-9:
                rejected = order.model_copy(
                    update={
                        "status": OrderStatus.REJECTED,
                        "reject_reason": "shorting_not_allowed",
                    }
                )
                return RiskDecision(False, rejected, "shorting_not_allowed")
            new_qty = current_position_qty - order.quantity
            new_position_value = new_qty * ref_price
            new_exposure = current_exposure - (current_position_qty * ref_price) + new_position_value

        if new_position_value > self.config.max_position_value + 1e-9:
            rejected = order.model_copy(
                update={
                    "status": OrderStatus.REJECTED,
                    "reject_reason": "max_position_value",
                }
            )
            return RiskDecision(False, rejected, "max_position_value")

        if new_exposure > self.config.max_total_exposure + 1e-9:
            rejected = order.model_copy(
                update={
                    "status": OrderStatus.REJECTED,
                    "reject_reason": "max_total_exposure",
                }
            )
            return RiskDecision(False, rejected, "max_total_exposure")

        accepted = order.model_copy(update={"status": OrderStatus.ACCEPTED})
        return RiskDecision(True, accepted, None)

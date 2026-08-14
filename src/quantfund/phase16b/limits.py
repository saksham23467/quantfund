"""Tiny default canary policy — never assume full account balance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CanaryPolicy:
    max_order_quantity: float = 1.0
    max_order_value: float = 1_000.0
    max_position_value: float = 2_000.0
    max_daily_loss: float = 500.0
    max_orders_per_day: int = 2
    max_turnover_per_day: float = 2_000.0
    capital_limit: float = 2_000.0
    allowed_instruments: tuple[str, ...] = ("RELIANCE",)
    allowed_sides: tuple[str, ...] = ("BUY",)
    allowed_order_types: tuple[str, ...] = ("MARKET",)
    allowed_products: tuple[str, ...] = ("CNC",)
    strategy_allowlist: tuple[str, ...] = ("buy_and_hold",)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_order_quantity": self.max_order_quantity,
            "max_order_value": self.max_order_value,
            "max_position_value": self.max_position_value,
            "max_daily_loss": self.max_daily_loss,
            "max_orders_per_day": self.max_orders_per_day,
            "max_turnover_per_day": self.max_turnover_per_day,
            "capital_limit": self.capital_limit,
            "allowed_instruments": list(self.allowed_instruments),
            "allowed_sides": list(self.allowed_sides),
            "allowed_order_types": list(self.allowed_order_types),
            "allowed_products": list(self.allowed_products),
            "strategy_allowlist": list(self.strategy_allowlist),
        }


def default_canary_policy() -> CanaryPolicy:
    return CanaryPolicy()


def policy_from_activation(activation) -> CanaryPolicy:
    return CanaryPolicy(
        max_order_quantity=activation.max_order_quantity,
        max_order_value=activation.max_order_value,
        max_position_value=activation.max_position_value,
        max_daily_loss=activation.max_daily_loss,
        max_orders_per_day=activation.max_orders_per_day,
        max_turnover_per_day=activation.max_turnover_per_day,
        capital_limit=activation.capital_limit,
        allowed_instruments=activation.allowed_instruments,
        allowed_sides=activation.allowed_sides,
        allowed_order_types=activation.allowed_order_types,
        allowed_products=activation.allowed_products,
        strategy_allowlist=(activation.strategy_id,),
    )

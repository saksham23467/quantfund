"""Pre-trade gates — ANY failure ⇒ no broker call."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.paper.kill_switch import KillSwitch
from quantfund.phase16b.activation import CanaryActivationRecord
from quantfund.phase16b.flags import LiveTradingFlag
from quantfund.phase16b.limits import CanaryPolicy
from quantfund.phase16b.market_data_gate import (
    LiveMarketQuote,
    evaluate_live_market_data,
)


@dataclass
class OrderIntent:
    strategy_id: str
    strategy_hash: str
    config_hash: str
    symbol: str
    side: str
    quantity: float
    order_type: str = "MARKET"
    product: str = "CNC"
    ref_price: float = 0.0
    intent_id: str = ""


@dataclass
class GateDecision:
    allowed: bool
    blockers: list[str] = field(default_factory=list)
    place_order_authorized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blockers": list(self.blockers),
            "place_order_authorized": self.place_order_authorized,
        }


@dataclass
class SessionCounters:
    orders_today: int = 0
    turnover_today: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    positions: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.positions is None:
            self.positions = {}

    @property
    def daily_loss(self) -> float:
        # positive loss amount
        pnl = self.realized_pnl + self.unrealized_pnl
        return max(0.0, -pnl)


def evaluate_pretrade_gates(
    intent: OrderIntent,
    *,
    live_flag: LiveTradingFlag,
    activation: CanaryActivationRecord | None,
    policy: CanaryPolicy,
    kill_switch: KillSwitch,
    kill_switch_disarmed_for_canary: bool,
    reconciliation_clean: bool,
    quote: LiveMarketQuote | None,
    counters: SessionCounters,
    mode: str,  # CANARY_SIMULATION | LIVE_CANARY
    require_live_flag: bool = True,
) -> GateDecision:
    blockers: list[str] = []

    if activation is None:
        blockers.append("missing_activation")
    else:
        blockers.extend(
            activation.validate_against(
                strategy_id=intent.strategy_id,
                strategy_hash=intent.strategy_hash,
                config_hash=intent.config_hash,
            )
        )

    if intent.strategy_id not in policy.strategy_allowlist:
        if "strategy_not_allowlisted" not in blockers:
            blockers.append("strategy_not_allowlisted")

    if mode == "LIVE_CANARY" and require_live_flag and not live_flag.enabled:
        blockers.append("live_flag_disabled")

    if kill_switch.is_triggered:
        blockers.append("kill_switch_triggered")
    elif not kill_switch_disarmed_for_canary:
        # ARMED means not disarmed for live canary
        blockers.append("kill_switch_armed")

    if not reconciliation_clean:
        blockers.append("reconciliation_mismatch")

    md = evaluate_live_market_data(quote)
    if not md.ok and md.reason:
        blockers.append(md.reason)

    side = intent.side.upper()
    otype = intent.order_type.upper()
    product = intent.product.upper()
    if intent.symbol not in policy.allowed_instruments:
        blockers.append("invalid_symbol")
    if side not in policy.allowed_sides:
        blockers.append("invalid_side")
    if otype not in policy.allowed_order_types:
        blockers.append("invalid_order_type")
    if product not in policy.allowed_products:
        blockers.append("invalid_product")

    qty = float(intent.quantity)
    price = float(intent.ref_price or (quote.price if quote else 0.0))
    value = qty * price
    if qty > policy.max_order_quantity + 1e-9:
        blockers.append("max_order_quantity")
    if value > policy.max_order_value + 1e-9:
        blockers.append("max_order_value")
    pos = float((counters.positions or {}).get(intent.symbol, 0.0))
    if side == "BUY":
        new_pos = pos + qty
    else:
        new_pos = pos - qty
    if abs(new_pos) * price > policy.max_position_value + 1e-9:
        blockers.append("max_position")
    if counters.daily_loss >= policy.max_daily_loss - 1e-9:
        blockers.append("max_daily_loss")
    if counters.orders_today >= policy.max_orders_per_day:
        blockers.append("max_orders_per_day")
    if counters.turnover_today + value > policy.max_turnover_per_day + 1e-9:
        blockers.append("max_turnover")
    if value > policy.capital_limit + 1e-9:
        blockers.append("insufficient_capital")

    allowed = len(blockers) == 0
    return GateDecision(
        allowed=allowed,
        blockers=blockers,
        place_order_authorized=allowed,
    )

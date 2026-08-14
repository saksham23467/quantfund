"""Live capital hierarchy — ceilings may only tighten toward live."""

from __future__ import annotations

from dataclasses import dataclass

from quantfund.paper.kill_switch import KillSwitch
from quantfund.trading.models import Order, OrderSide


@dataclass(frozen=True)
class CapitalLimits:
    """One level of the capital hierarchy."""

    max_order_notional: float
    max_position_notional: float
    max_gross_exposure: float
    max_daily_loss: float | None = None
    max_turnover: float | None = None
    max_order_count: int | None = None
    max_capital_allocation: float | None = None


def _min_optional(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def merge_capital_limits(*levels: CapitalLimits) -> CapitalLimits:
    """strategy ≤ session ≤ account ≤ platform via pairwise min (tighten only)."""
    if not levels:
        raise ValueError("at least one capital level required")
    acc = levels[0]
    for lvl in levels[1:]:
        moc_a, moc_b = acc.max_order_count, lvl.max_order_count
        if moc_a is None and moc_b is None:
            moc: int | None = None
        elif moc_a is None:
            moc = moc_b
        elif moc_b is None:
            moc = moc_a
        else:
            moc = min(moc_a, moc_b)
        acc = CapitalLimits(
            max_order_notional=min(acc.max_order_notional, lvl.max_order_notional),
            max_position_notional=min(
                acc.max_position_notional, lvl.max_position_notional
            ),
            max_gross_exposure=min(acc.max_gross_exposure, lvl.max_gross_exposure),
            max_daily_loss=_min_optional(acc.max_daily_loss, lvl.max_daily_loss),
            max_turnover=_min_optional(acc.max_turnover, lvl.max_turnover),
            max_order_count=moc,
            max_capital_allocation=_min_optional(
                acc.max_capital_allocation, lvl.max_capital_allocation
            ),
        )
    return acc


PLATFORM_SAFETY_LIMITS = CapitalLimits(
    max_order_notional=100_000.0,
    max_position_notional=100_000.0,
    max_gross_exposure=100_000.0,
    max_daily_loss=25_000.0,
    max_turnover=500_000.0,
    max_order_count=100,
    max_capital_allocation=100_000.0,
)


@dataclass
class LiveRiskDecision:
    accepted: bool
    reason: str | None = None


class LiveRiskEngine:
    """Compose kill switch + merged capital hierarchy (freeze-only kill)."""

    def __init__(
        self,
        *,
        strategy_limits: CapitalLimits,
        session_limits: CapitalLimits,
        account_limits: CapitalLimits,
        platform_limits: CapitalLimits = PLATFORM_SAFETY_LIMITS,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        self.effective = merge_capital_limits(
            strategy_limits, session_limits, account_limits, platform_limits
        )
        if self.effective.max_order_notional > platform_limits.max_order_notional + 1e-9:
            raise ValueError("capital_hierarchy_violation")
        self.kill_switch = kill_switch or KillSwitch()
        self.order_count = 0
        self.turnover = 0.0

    def check_order(
        self,
        order: Order,
        *,
        ref_price: float,
        position_qty: float,
        exposure: float,
        equity: float = 0.0,
        session_capital_used: float = 0.0,
        day_start_equity: float | None = None,
    ) -> LiveRiskDecision:
        if self.kill_switch.is_triggered:
            return LiveRiskDecision(False, "kill_switch")

        if order.side == OrderSide.SELL and order.quantity > position_qty + 1e-9:
            return LiveRiskDecision(False, "shorting_not_allowed")

        notional = order.quantity * ref_price
        if notional > self.effective.max_order_notional + 1e-9:
            return LiveRiskDecision(False, "max_order_notional")

        if order.side == OrderSide.BUY:
            new_qty = position_qty + order.quantity
        else:
            new_qty = position_qty - order.quantity
        new_pos_notional = max(0.0, new_qty) * ref_price
        if new_pos_notional > self.effective.max_position_notional + 1e-9:
            return LiveRiskDecision(False, "max_position_notional")

        new_exposure = exposure - (position_qty * ref_price) + new_pos_notional
        if new_exposure > self.effective.max_gross_exposure + 1e-9:
            return LiveRiskDecision(False, "max_gross_exposure")

        if (
            self.effective.max_order_count is not None
            and self.order_count >= self.effective.max_order_count
        ):
            return LiveRiskDecision(False, "max_order_count")

        if self.effective.max_turnover is not None:
            if self.turnover + notional > self.effective.max_turnover + 1e-9:
                return LiveRiskDecision(False, "max_turnover")

        if (
            self.effective.max_daily_loss is not None
            and day_start_equity is not None
            and (day_start_equity - equity) > self.effective.max_daily_loss + 1e-9
        ):
            return LiveRiskDecision(False, "max_daily_loss")

        if (
            self.effective.max_capital_allocation is not None
            and order.side == OrderSide.BUY
            and session_capital_used + notional
            > self.effective.max_capital_allocation + 1e-9
        ):
            return LiveRiskDecision(False, "max_capital_allocation")

        return LiveRiskDecision(True, None)

    def record_accepted(self, *, notional: float) -> None:
        self.order_count += 1
        self.turnover += notional

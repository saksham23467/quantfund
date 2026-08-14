"""Shared long-only sizing helpers for baselines."""

from __future__ import annotations

from quantfund.strategies.base import StrategyContext
from quantfund.trading.models import Signal, SignalAction


def hold(context: StrategyContext, symbol: str, **meta) -> Signal:
    return Signal(
        timestamp=context.timestamp,
        symbol=symbol,
        action=SignalAction.HOLD,
        metadata=meta,
    )


def buy_shares(context: StrategyContext, symbol: str, allocation: float = 0.95) -> Signal:
    bar = context.current_bar
    if bar is None:
        return hold(context, symbol, reason="no_bar")
    if context.membership == "UNKNOWN":
        return hold(context, symbol, reason="membership_unknown")
    if context.membership == "FALSE":
        return hold(context, symbol, reason="not_in_universe")
    spend = context.cash * allocation
    qty = int(spend // bar.close)
    if qty <= 0:
        return hold(context, symbol, reason="insufficient_cash")
    return Signal(
        timestamp=context.timestamp,
        symbol=symbol,
        action=SignalAction.BUY,
        target_quantity=float(qty),
        metadata={"sizing_price_ref": bar.close},
    )


def sell_all(context: StrategyContext, symbol: str) -> Signal:
    if context.membership == "UNKNOWN":
        return hold(context, symbol, reason="membership_unknown")
    qty = context.position_quantity
    if qty <= 0:
        return hold(context, symbol, reason="flat")
    return Signal(
        timestamp=context.timestamp,
        symbol=symbol,
        action=SignalAction.SELL,
        target_quantity=float(qty),
    )

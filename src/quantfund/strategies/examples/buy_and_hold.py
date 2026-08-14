"""Deterministic buy-and-hold strategy for smoke-testing the backtester.

Not optimized. Not claimed to be profitable. Infrastructure validation only.
"""

from __future__ import annotations

from quantfund.data.models import MarketBar
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.trading.models import Signal, SignalAction


class BuyAndHoldStrategy(Strategy):
    """Buy once on the first bar with sufficient cash; hold thereafter."""

    def __init__(
        self,
        *,
        symbol: str,
        allocation: float = 1.0,
        strategy_version: str = "1.0.0",
        code_version: str = "0.1.0",
    ) -> None:
        if not 0 < allocation <= 1:
            raise ValueError("allocation must be in (0, 1]")
        self.symbol = symbol
        self.allocation = allocation
        self._strategy_version = strategy_version
        self._code_version = code_version
        self._purchased = False

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="buy_and_hold",
            strategy_name="Buy and Hold",
            strategy_version=self._strategy_version,
            parameters={"symbol": self.symbol, "allocation": self.allocation},
            code_version=self._code_version,
        )

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        return [b for b in bars if b.symbol == self.symbol]

    def generate_signal(self, context: StrategyContext) -> Signal:
        bar = context.current_bar
        if bar is None:
            return Signal(
                timestamp=context.timestamp,
                symbol=self.symbol,
                action=SignalAction.HOLD,
            )

        if context.position_quantity > 0 or self._purchased:
            return Signal(
                timestamp=context.timestamp,
                symbol=self.symbol,
                action=SignalAction.HOLD,
            )

        # Quantity is sized using the signal bar close as an estimate only.
        # Actual fill occurs at next-bar open via the broker simulator.
        spend = context.cash * self.allocation
        est_price = bar.close
        qty = int(spend // est_price)
        if qty <= 0:
            return Signal(
                timestamp=context.timestamp,
                symbol=self.symbol,
                action=SignalAction.HOLD,
                metadata={"reason": "insufficient_cash_for_one_share"},
            )

        self._purchased = True
        return Signal(
            timestamp=context.timestamp,
            symbol=self.symbol,
            action=SignalAction.BUY,
            target_quantity=float(qty),
            metadata={"sizing_price_ref": est_price, "note": "fill_at_next_open"},
        )

"""Momentum baseline (not optimized)."""

from __future__ import annotations

from quantfund.data.models import MarketBar
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.strategies.baselines._sizing import buy_shares, hold, sell_all
from quantfund.trading.models import Signal


class MomentumStrategy(Strategy):
    def __init__(
        self,
        *,
        symbol: str,
        lookback: int = 3,
        threshold: float = 0.0,
        allocation: float = 0.95,
        strategy_version: str = "1.0.0",
    ) -> None:
        self.symbol = symbol
        self.lookback = lookback
        self.threshold = threshold
        self.allocation = allocation
        self._version = strategy_version

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="momentum",
            strategy_name="Momentum",
            strategy_version=self._version,
            parameters={
                "symbol": self.symbol,
                "lookback": self.lookback,
                "threshold": self.threshold,
                "allocation": self.allocation,
            },
            description="Long when momentum_n > threshold. Baseline only.",
            required_features=[f"momentum_{self.lookback}"],
            parameter_schema={"lookback": {"type": "integer", "minimum": 1}},
        )

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        return [b for b in bars if b.symbol == self.symbol]

    def generate_signal(self, context: StrategyContext) -> Signal:
        if context.membership == "UNKNOWN":
            return hold(context, self.symbol, reason="membership_unknown")
        key = f"momentum_{self.lookback}"
        mom = context.feature(key)
        if mom is None:
            closes = [b.close for b in context.history]
            if len(closes) <= self.lookback:
                return hold(context, self.symbol, reason="warmup")
            mom = closes[-1] / closes[-1 - self.lookback] - 1.0
        if mom > self.threshold and context.position_quantity <= 0:
            return buy_shares(context, self.symbol, self.allocation)
        if mom <= self.threshold and context.position_quantity > 0:
            return sell_all(context, self.symbol)
        return hold(context, self.symbol)

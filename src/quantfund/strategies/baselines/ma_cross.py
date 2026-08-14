"""Moving-average crossover baseline (not optimized)."""

from __future__ import annotations

from quantfund.data.models import MarketBar
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.strategies.baselines._sizing import buy_shares, hold, sell_all
from quantfund.trading.models import Signal


class MovingAverageCrossStrategy(Strategy):
    def __init__(
        self,
        *,
        symbol: str,
        fast: int = 3,
        slow: int = 5,
        allocation: float = 0.95,
        strategy_version: str = "1.0.0",
    ) -> None:
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self.symbol = symbol
        self.fast = fast
        self.slow = slow
        self.allocation = allocation
        self._version = strategy_version

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="ma_cross",
            strategy_name="Moving Average Crossover",
            strategy_version=self._version,
            parameters={
                "symbol": self.symbol,
                "fast": self.fast,
                "slow": self.slow,
                "allocation": self.allocation,
            },
            description="Long when SMA_fast > SMA_slow; flat otherwise. Baseline only.",
            required_features=[f"sma_{self.fast}", f"sma_{self.slow}"],
            parameter_schema={
                "fast": {"type": "integer", "minimum": 1},
                "slow": {"type": "integer", "minimum": 2},
            },
        )

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        return [b for b in bars if b.symbol == self.symbol]

    def generate_signal(self, context: StrategyContext) -> Signal:
        if context.membership == "UNKNOWN":
            return hold(context, self.symbol, reason="membership_unknown")
        fast_key, slow_key = f"sma_{self.fast}", f"sma_{self.slow}"
        fast = context.feature(fast_key)
        slow = context.feature(slow_key)
        if fast is None or slow is None:
            # Fallback from history for M1-style runs without FeatureEngine
            closes = [b.close for b in context.history]
            if len(closes) < self.slow:
                return hold(context, self.symbol, reason="warmup")
            fast = sum(closes[-self.fast :]) / self.fast
            slow = sum(closes[-self.slow :]) / self.slow
        long_signal = fast > slow
        if long_signal and context.position_quantity <= 0:
            return buy_shares(context, self.symbol, self.allocation)
        if (not long_signal) and context.position_quantity > 0:
            return sell_all(context, self.symbol)
        return hold(context, self.symbol)

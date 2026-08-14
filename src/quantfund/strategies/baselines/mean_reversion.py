"""Mean-reversion z-score baseline (not optimized)."""

from __future__ import annotations

from quantfund.data.models import MarketBar
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.strategies.baselines._sizing import buy_shares, hold, sell_all
from quantfund.trading.models import Signal


class MeanReversionStrategy(Strategy):
    def __init__(
        self,
        *,
        symbol: str,
        window: int = 5,
        entry_z: float = -1.0,
        exit_z: float = 0.0,
        allocation: float = 0.95,
        strategy_version: str = "1.0.0",
    ) -> None:
        self.symbol = symbol
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.allocation = allocation
        self._version = strategy_version

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="mean_reversion",
            strategy_name="Mean Reversion",
            strategy_version=self._version,
            parameters={
                "symbol": self.symbol,
                "window": self.window,
                "entry_z": self.entry_z,
                "exit_z": self.exit_z,
                "allocation": self.allocation,
            },
            description="Long when z-score < entry_z; exit when z-score >= exit_z.",
            required_features=[f"zscore_{self.window}"],
            parameter_schema={"window": {"type": "integer", "minimum": 2}},
        )

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        return [b for b in bars if b.symbol == self.symbol]

    def generate_signal(self, context: StrategyContext) -> Signal:
        if context.membership == "UNKNOWN":
            return hold(context, self.symbol, reason="membership_unknown")
        key = f"zscore_{self.window}"
        z = context.feature(key)
        if z is None:
            closes = [b.close for b in context.history]
            if len(closes) < self.window:
                return hold(context, self.symbol, reason="warmup")
            window = closes[-self.window :]
            mean = sum(window) / len(window)
            var = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
            std = var**0.5
            if std == 0:
                return hold(context, self.symbol, reason="zero_std")
            z = (closes[-1] - mean) / std
        if context.position_quantity <= 0 and z < self.entry_z:
            return buy_shares(context, self.symbol, self.allocation)
        if context.position_quantity > 0 and z >= self.exit_z:
            return sell_all(context, self.symbol)
        return hold(context, self.symbol)

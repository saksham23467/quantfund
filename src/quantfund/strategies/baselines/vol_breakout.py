"""Volatility breakout baseline (not optimized)."""

from __future__ import annotations

from quantfund.data.models import MarketBar
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.strategies.baselines._sizing import buy_shares, hold, sell_all
from quantfund.trading.models import Signal


class VolatilityBreakoutStrategy(Strategy):
    def __init__(
        self,
        *,
        symbol: str,
        atr_n: int = 3,
        k: float = 0.5,
        allocation: float = 0.95,
        strategy_version: str = "1.0.0",
    ) -> None:
        self.symbol = symbol
        self.atr_n = atr_n
        self.k = k
        self.allocation = allocation
        self._version = strategy_version

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="vol_breakout",
            strategy_name="Volatility Breakout",
            strategy_version=self._version,
            parameters={
                "symbol": self.symbol,
                "atr_n": self.atr_n,
                "k": self.k,
                "allocation": self.allocation,
            },
            description="Long when close > prior close + k*ATR. Baseline only.",
            required_features=[f"atr_{self.atr_n}"],
            parameter_schema={"atr_n": {"type": "integer", "minimum": 1}},
        )

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        return [b for b in bars if b.symbol == self.symbol]

    def generate_signal(self, context: StrategyContext) -> Signal:
        if context.membership == "UNKNOWN":
            return hold(context, self.symbol, reason="membership_unknown")
        atr = context.feature(f"atr_{self.atr_n}")
        hist = context.history
        if len(hist) < self.atr_n + 1:
            return hold(context, self.symbol, reason="warmup")
        if atr is None:
            trs = []
            for i in range(-self.atr_n, 0):
                b = hist[i]
                prev = hist[i - 1].close
                tr = max(b.high - b.low, abs(b.high - prev), abs(b.low - prev))
                trs.append(tr)
            atr = sum(trs) / len(trs)
        prior_close = hist[-2].close
        close = hist[-1].close
        level = prior_close + self.k * atr
        if close > level and context.position_quantity <= 0:
            return buy_shares(context, self.symbol, self.allocation)
        if close <= level and context.position_quantity > 0:
            return sell_all(context, self.symbol)
        return hold(context, self.symbol)

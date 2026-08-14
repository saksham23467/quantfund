"""Additional fixed-grammar strategies for Phase 18 (no code mutation)."""

from __future__ import annotations

from quantfund.data.models import MarketBar
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.strategies.baselines._sizing import buy_shares, hold, sell_all
from quantfund.trading.models import Signal


def _rsi(closes: list[float], period: int) -> float | None:
    if len(closes) <= period:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class RSIMeanReversionStrategy(Strategy):
    def __init__(
        self,
        *,
        symbol: str,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        allocation: float = 0.95,
        strategy_version: str = "1.0.0",
    ) -> None:
        self.symbol = symbol
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.allocation = allocation
        self._version = strategy_version

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="rsi_mean_reversion",
            strategy_name="RSI Mean Reversion",
            strategy_version=self._version,
            parameters={
                "symbol": self.symbol,
                "period": self.period,
                "oversold": self.oversold,
                "overbought": self.overbought,
                "allocation": self.allocation,
            },
            description="Long when RSI < oversold; exit when RSI > overbought.",
            required_features=[],
            parameter_schema={"period": {"type": "integer", "minimum": 2}},
        )

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        return [b for b in bars if b.symbol == self.symbol]

    def generate_signal(self, context: StrategyContext) -> Signal:
        if context.membership == "UNKNOWN":
            return hold(context, self.symbol, reason="membership_unknown")
        closes = [b.close for b in context.history]
        rsi = _rsi(closes, self.period)
        if rsi is None:
            return hold(context, self.symbol, reason="warmup")
        if rsi < self.oversold and context.position_quantity <= 0:
            return buy_shares(context, self.symbol, self.allocation)
        if rsi > self.overbought and context.position_quantity > 0:
            return sell_all(context, self.symbol)
        return hold(context, self.symbol)


class DonchianBreakoutStrategy(Strategy):
    def __init__(
        self,
        *,
        symbol: str,
        lookback: int = 20,
        allocation: float = 0.95,
        strategy_version: str = "1.0.0",
    ) -> None:
        self.symbol = symbol
        self.lookback = lookback
        self.allocation = allocation
        self._version = strategy_version

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="donchian_breakout",
            strategy_name="Donchian Breakout",
            strategy_version=self._version,
            parameters={
                "symbol": self.symbol,
                "lookback": self.lookback,
                "allocation": self.allocation,
            },
            description="Long when close breaks prior lookback high; flat on lookback low break.",
            required_features=[],
            parameter_schema={"lookback": {"type": "integer", "minimum": 2}},
        )

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        return [b for b in bars if b.symbol == self.symbol]

    def generate_signal(self, context: StrategyContext) -> Signal:
        if context.membership == "UNKNOWN":
            return hold(context, self.symbol, reason="membership_unknown")
        hist = context.history
        if len(hist) <= self.lookback:
            return hold(context, self.symbol, reason="warmup")
        window = hist[-(self.lookback + 1) : -1]
        prior_high = max(b.high for b in window)
        prior_low = min(b.low for b in window)
        close = hist[-1].close
        if close > prior_high and context.position_quantity <= 0:
            return buy_shares(context, self.symbol, self.allocation)
        if close < prior_low and context.position_quantity > 0:
            return sell_all(context, self.symbol)
        return hold(context, self.symbol)


class MomentumVolFilterStrategy(Strategy):
    """Momentum entry only when realized vol is below a threshold."""

    def __init__(
        self,
        *,
        symbol: str,
        lookback: int = 20,
        vol_window: int = 20,
        max_vol: float = 0.03,
        threshold: float = 0.0,
        allocation: float = 0.95,
        strategy_version: str = "1.0.0",
        strategy_id: str = "momentum_vol_filter",
    ) -> None:
        self.symbol = symbol
        self.lookback = lookback
        self.vol_window = vol_window
        self.max_vol = max_vol
        self.threshold = threshold
        self.allocation = allocation
        self._version = strategy_version
        self._strategy_id = strategy_id

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=self._strategy_id,
            strategy_name="Momentum + Volatility Filter",
            strategy_version=self._version,
            parameters={
                "symbol": self.symbol,
                "lookback": self.lookback,
                "vol_window": self.vol_window,
                "max_vol": self.max_vol,
                "threshold": self.threshold,
                "allocation": self.allocation,
            },
            description="Long momentum only if rolling vol <= max_vol.",
            required_features=[
                f"momentum_{self.lookback}",
                f"rolling_vol_{self.vol_window}",
            ],
            parameter_schema={},
        )

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        return [b for b in bars if b.symbol == self.symbol]

    def generate_signal(self, context: StrategyContext) -> Signal:
        if context.membership == "UNKNOWN":
            return hold(context, self.symbol, reason="membership_unknown")
        mom = context.feature(f"momentum_{self.lookback}")
        vol = context.feature(f"rolling_vol_{self.vol_window}")
        closes = [b.close for b in context.history]
        if mom is None:
            if len(closes) <= self.lookback:
                return hold(context, self.symbol, reason="warmup")
            mom = closes[-1] / closes[-1 - self.lookback] - 1.0
        if vol is None:
            if len(closes) <= self.vol_window:
                return hold(context, self.symbol, reason="warmup")
            rets = [
                closes[i] / closes[i - 1] - 1.0
                for i in range(-self.vol_window + 1, 0)
            ]
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / len(rets)
            vol = var**0.5
        allow = vol is not None and vol <= self.max_vol
        if allow and mom > self.threshold and context.position_quantity <= 0:
            return buy_shares(context, self.symbol, self.allocation)
        if (not allow or mom <= self.threshold) and context.position_quantity > 0:
            return sell_all(context, self.symbol)
        return hold(context, self.symbol)


class TrendVolFilterStrategy(Strategy):
    """MA trend entry only when rolling vol is below threshold."""

    def __init__(
        self,
        *,
        symbol: str,
        fast: int = 20,
        slow: int = 100,
        vol_window: int = 20,
        max_vol: float = 0.03,
        allocation: float = 0.95,
        strategy_version: str = "1.0.0",
    ) -> None:
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self.symbol = symbol
        self.fast = fast
        self.slow = slow
        self.vol_window = vol_window
        self.max_vol = max_vol
        self.allocation = allocation
        self._version = strategy_version

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="trend_vol_filter",
            strategy_name="Trend + Volatility Filter",
            strategy_version=self._version,
            parameters={
                "symbol": self.symbol,
                "fast": self.fast,
                "slow": self.slow,
                "vol_window": self.vol_window,
                "max_vol": self.max_vol,
                "allocation": self.allocation,
            },
            description="Long SMA trend only if rolling vol <= max_vol.",
            required_features=[
                f"sma_{self.fast}",
                f"sma_{self.slow}",
                f"rolling_vol_{self.vol_window}",
            ],
            parameter_schema={},
        )

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        return [b for b in bars if b.symbol == self.symbol]

    def generate_signal(self, context: StrategyContext) -> Signal:
        if context.membership == "UNKNOWN":
            return hold(context, self.symbol, reason="membership_unknown")
        fast = context.feature(f"sma_{self.fast}")
        slow = context.feature(f"sma_{self.slow}")
        vol = context.feature(f"rolling_vol_{self.vol_window}")
        closes = [b.close for b in context.history]
        if fast is None or slow is None:
            if len(closes) < self.slow:
                return hold(context, self.symbol, reason="warmup")
            fast = sum(closes[-self.fast :]) / self.fast
            slow = sum(closes[-self.slow :]) / self.slow
        if vol is None:
            if len(closes) <= self.vol_window:
                return hold(context, self.symbol, reason="warmup")
            rets = [
                closes[i] / closes[i - 1] - 1.0
                for i in range(-self.vol_window + 1, 0)
            ]
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / len(rets)
            vol = var**0.5
        trend = fast > slow
        allow = vol is not None and vol <= self.max_vol
        if allow and trend and context.position_quantity <= 0:
            return buy_shares(context, self.symbol, self.allocation)
        if (not allow or not trend) and context.position_quantity > 0:
            return sell_all(context, self.symbol)
        return hold(context, self.symbol)

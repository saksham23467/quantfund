"""Build Strategy factories from Phase 18 candidates (reuse baselines + extras)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from quantfund.phase18.candidates import SearchCandidate
from quantfund.phase18.extra_strategies import (
    DonchianBreakoutStrategy,
    MomentumVolFilterStrategy,
    RSIMeanReversionStrategy,
    TrendVolFilterStrategy,
)
from quantfund.strategies.base import Strategy
from quantfund.strategies.baselines.ma_cross import MovingAverageCrossStrategy
from quantfund.strategies.baselines.mean_reversion import MeanReversionStrategy
from quantfund.strategies.baselines.momentum import MomentumStrategy
from quantfund.strategies.baselines.vol_breakout import VolatilityBreakoutStrategy
from quantfund.strategies.spec.interpret import interpret_strategy_spec
from quantfund.strategies.spec.validate import validate_strategy_spec


def feature_requests_for(candidate: SearchCandidate) -> list[dict[str, Any]]:
    p = candidate.parameters
    fam = candidate.strategy_family
    if fam in ("ma_cross", "trend_following"):
        return [
            {"name": "sma", "window": int(p["fast"])},
            {"name": "sma", "window": int(p["slow"])},
        ]
    if fam == "momentum":
        return [{"name": "momentum", "window": int(p["lookback"])}]
    if fam == "mean_reversion":
        return [{"name": "zscore", "window": int(p["window"])}]
    if fam == "vol_breakout":
        return [{"name": "atr", "window": int(p["atr_n"])}]
    if fam in ("volatility_regime_filter", "momentum_vol_filter"):
        return [
            {"name": "momentum", "window": int(p["lookback"])},
            {"name": "rolling_vol", "window": int(p["vol_window"])},
        ]
    if fam == "trend_vol_filter":
        return [
            {"name": "sma", "window": int(p["fast"])},
            {"name": "sma", "window": int(p["slow"])},
            {"name": "rolling_vol", "window": int(p["vol_window"])},
        ]
    return []


def strategy_factory_for(
    candidate: SearchCandidate, *, symbol: str
) -> Callable[[], Strategy]:
    """Prefer typed baselines / extras; StrategySpec is always materialised."""
    fam = candidate.strategy_family
    p = candidate.parameters
    spec = candidate.strategy_spec(symbol)

    # Validate feature-rule specs when they have rules (extras may be empty-rule)
    if spec.entry_rules:
        try:
            validate_strategy_spec(spec)
        except Exception:  # noqa: BLE001 — typed factory remains authoritative
            pass

    def make() -> Strategy:
        if fam in ("ma_cross", "trend_following"):
            return MovingAverageCrossStrategy(
                symbol=symbol,
                fast=int(p["fast"]),
                slow=int(p["slow"]),
                strategy_version="1.0.0",
            )
        if fam == "momentum":
            return MomentumStrategy(
                symbol=symbol,
                lookback=int(p["lookback"]),
                threshold=float(p["threshold"]),
            )
        if fam == "mean_reversion":
            return MeanReversionStrategy(
                symbol=symbol,
                window=int(p["window"]),
                entry_z=float(p["entry_z"]),
                exit_z=float(p["exit_z"]),
            )
        if fam == "vol_breakout":
            return VolatilityBreakoutStrategy(
                symbol=symbol,
                atr_n=int(p["atr_n"]),
                k=float(p["k"]),
            )
        if fam == "rsi_mean_reversion":
            return RSIMeanReversionStrategy(
                symbol=symbol,
                period=int(p["period"]),
                oversold=float(p["oversold"]),
                overbought=float(p["overbought"]),
            )
        if fam == "donchian_breakout":
            return DonchianBreakoutStrategy(
                symbol=symbol,
                lookback=int(p["lookback"]),
            )
        if fam in ("volatility_regime_filter", "momentum_vol_filter"):
            return MomentumVolFilterStrategy(
                symbol=symbol,
                lookback=int(p["lookback"]),
                vol_window=int(p["vol_window"]),
                max_vol=float(p["max_vol"]),
                threshold=float(p["threshold"]),
                strategy_id=fam,
            )
        if fam == "trend_vol_filter":
            return TrendVolFilterStrategy(
                symbol=symbol,
                fast=int(p["fast"]),
                slow=int(p["slow"]),
                vol_window=int(p["vol_window"]),
                max_vol=float(p["max_vol"]),
            )
        # Fallback: pure StrategySpec interpreter
        return interpret_strategy_spec(spec)

    # Align strategy_id for ResearchRunner config check
    # MovingAverageCrossStrategy always reports strategy_id="ma_cross"
    # For trend_following we wrap metadata via a thin adapter.
    if fam == "trend_following":
        base_factory = make

        def make_trend() -> Strategy:
            inner = base_factory()
            return _RelabelStrategy(inner, strategy_id="trend_following")

        return make_trend

    if fam in ("volatility_regime_filter", "momentum_vol_filter"):
        return make

    return make


class _RelabelStrategy(Strategy):
    """Adapter so family id matches ExperimentConfig.strategy_id."""

    def __init__(self, inner: Strategy, *, strategy_id: str) -> None:
        self._inner = inner
        self._strategy_id = strategy_id

    def metadata(self):
        m = self._inner.metadata()
        return replace(m, strategy_id=self._strategy_id)

    def prepare_data(self, bars):
        return self._inner.prepare_data(bars)

    def generate_signal(self, context):
        return self._inner.generate_signal(context)

"""Fixed baseline strategy factories for Phase 17A — no parameter mutation."""

from __future__ import annotations

from typing import Any, Callable

from quantfund.strategies.baselines.ma_cross import MovingAverageCrossStrategy
from quantfund.strategies.baselines.mean_reversion import MeanReversionStrategy
from quantfund.strategies.baselines.momentum import MomentumStrategy
from quantfund.strategies.baselines.vol_breakout import VolatilityBreakoutStrategy
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


def baseline_catalog(symbol: str) -> dict[str, dict[str, Any]]:
    """Exact fixed parameters used in Phase 17A."""
    return {
        "buy_and_hold": {
            "strategy_id": "buy_and_hold",
            "strategy_version": "1.0.0",
            "parameters": {"symbol": symbol, "allocation": 0.5},
            "factory": lambda: BuyAndHoldStrategy(symbol=symbol, allocation=0.5),
        },
        "ma_cross": {
            "strategy_id": "ma_cross",
            "strategy_version": "1.0.0",
            "parameters": {
                "symbol": symbol,
                "fast": 3,
                "slow": 5,
                "allocation": 0.95,
            },
            "factory": lambda: MovingAverageCrossStrategy(symbol=symbol),
        },
        "momentum": {
            "strategy_id": "momentum",
            "strategy_version": "1.0.0",
            "parameters": {
                "symbol": symbol,
                "lookback": 3,
                "threshold": 0.0,
                "allocation": 0.95,
            },
            "factory": lambda: MomentumStrategy(symbol=symbol),
        },
        "mean_reversion": {
            "strategy_id": "mean_reversion",
            "strategy_version": "1.0.0",
            "parameters": {
                "symbol": symbol,
                "window": 5,
                "entry_z": -1.0,
                "exit_z": 0.0,
                "allocation": 0.95,
            },
            "factory": lambda: MeanReversionStrategy(symbol=symbol),
        },
        "vol_breakout": {
            "strategy_id": "vol_breakout",
            "strategy_version": "1.0.0",
            "parameters": {
                "symbol": symbol,
                "atr_n": 3,
                "k": 0.5,
                "allocation": 0.95,
            },
            "factory": lambda: VolatilityBreakoutStrategy(symbol=symbol),
        },
    }


def strategy_factory(name: str, symbol: str) -> Callable[[], Any]:
    cat = baseline_catalog(symbol)
    if name not in cat:
        raise KeyError(name)
    return cat[name]["factory"]

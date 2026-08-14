"""Fixed strategy grammar — explicit parameter grids only (no arbitrary code)."""

from __future__ import annotations

from typing import Any, Literal

SearchMode = Literal["full", "demo", "tiny"]

FAMILY_IDS = (
    "ma_cross",
    "momentum",
    "mean_reversion",
    "vol_breakout",
    "trend_following",
    "rsi_mean_reversion",
    "donchian_breakout",
    "volatility_regime_filter",
    "momentum_vol_filter",
    "trend_vol_filter",
)

# Explicit grids from Phase 18 brief
GRIDS_FULL: dict[str, dict[str, tuple[Any, ...]]] = {
    "ma_cross": {
        "fast": (5, 10, 20, 30),
        "slow": (50, 100, 150, 200),
    },
    "momentum": {
        "lookback": (10, 20, 40, 60, 120),
        "threshold": (0.0,),
    },
    "mean_reversion": {
        "window": (10, 20, 40),
        "entry_z": (-2.0, -1.5, -1.0),
        "exit_z": (0.0,),
    },
    "vol_breakout": {
        "atr_n": (10, 20, 40),
        "k": (0.5, 1.0, 1.5),
    },
    "trend_following": {
        "fast": (20, 30),
        "slow": (100, 150, 200),
    },
    "rsi_mean_reversion": {
        "period": (14, 21),
        "oversold": (30.0,),
        "overbought": (70.0,),
    },
    "donchian_breakout": {
        "lookback": (20, 40, 60),
    },
    "volatility_regime_filter": {
        "lookback": (20, 40),
        "vol_window": (20,),
        "max_vol": (0.02, 0.03),
        "threshold": (0.0,),
    },
    "momentum_vol_filter": {
        "lookback": (20, 40, 60),
        "vol_window": (20,),
        "max_vol": (0.02, 0.03),
        "threshold": (0.0,),
    },
    "trend_vol_filter": {
        "fast": (20, 30),
        "slow": (100, 150),
        "vol_window": (20,),
        "max_vol": (0.02, 0.03),
    },
}

GRIDS_DEMO: dict[str, dict[str, tuple[Any, ...]]] = {
    "ma_cross": {"fast": (10, 20), "slow": (50, 100)},
    "momentum": {"lookback": (20, 60), "threshold": (0.0,)},
    "mean_reversion": {"window": (20,), "entry_z": (-1.5,), "exit_z": (0.0,)},
    "vol_breakout": {"atr_n": (20,), "k": (1.0,)},
    "trend_following": {"fast": (20,), "slow": (100,)},
    "rsi_mean_reversion": {"period": (14,), "oversold": (30.0,), "overbought": (70.0,)},
    "donchian_breakout": {"lookback": (20, 40)},
    "volatility_regime_filter": {
        "lookback": (20,),
        "vol_window": (20,),
        "max_vol": (0.03,),
        "threshold": (0.0,),
    },
    "momentum_vol_filter": {
        "lookback": (40,),
        "vol_window": (20,),
        "max_vol": (0.03,),
        "threshold": (0.0,),
    },
    "trend_vol_filter": {
        "fast": (20,),
        "slow": (100,),
        "vol_window": (20,),
        "max_vol": (0.03,),
    },
}

GRIDS_TINY: dict[str, dict[str, tuple[Any, ...]]] = {
    "ma_cross": {"fast": (5,), "slow": (20,)},
    "momentum": {"lookback": (10,), "threshold": (0.0,)},
    "mean_reversion": {"window": (10,), "entry_z": (-1.0,), "exit_z": (0.0,)},
    "vol_breakout": {"atr_n": (5,), "k": (0.5,)},
    "trend_following": {"fast": (5,), "slow": (20,)},
    "rsi_mean_reversion": {"period": (14,), "oversold": (30.0,), "overbought": (70.0,)},
    "donchian_breakout": {"lookback": (10,)},
    "volatility_regime_filter": {
        "lookback": (10,),
        "vol_window": (10,),
        "max_vol": (0.05,),
        "threshold": (0.0,),
    },
    "momentum_vol_filter": {
        "lookback": (10,),
        "vol_window": (10,),
        "max_vol": (0.05,),
        "threshold": (0.0,),
    },
    "trend_vol_filter": {
        "fast": (5,),
        "slow": (20,),
        "vol_window": (10,),
        "max_vol": (0.05,),
    },
}


def grids_for_mode(mode: SearchMode) -> dict[str, dict[str, tuple[Any, ...]]]:
    if mode == "full":
        return GRIDS_FULL
    if mode == "demo":
        return GRIDS_DEMO
    if mode == "tiny":
        return GRIDS_TINY
    raise ValueError(f"unknown search mode: {mode}")


def _product(params: dict[str, tuple[Any, ...]]) -> list[dict[str, Any]]:
    keys = list(params.keys())
    if not keys:
        return [{}]
    out: list[dict[str, Any]] = [{}]
    for key in keys:
        nxt: list[dict[str, Any]] = []
        for base in out:
            for val in params[key]:
                row = dict(base)
                row[key] = val
                nxt.append(row)
        out = nxt
    return out


def expand_family_params(
    family: str, grids: dict[str, dict[str, tuple[Any, ...]]]
) -> list[dict[str, Any]]:
    raw = _product(grids[family])
    if family in ("ma_cross", "trend_following", "trend_vol_filter"):
        return [p for p in raw if int(p["fast"]) < int(p["slow"])]
    return raw


def search_config_payload(mode: SearchMode) -> dict[str, Any]:
    grids = grids_for_mode(mode)
    return {
        "phase": "18",
        "mode": mode,
        "families": list(FAMILY_IDS),
        "grids": {k: {pk: list(pv) for pk, pv in v.items()} for k, v in grids.items()},
        "cost_model": "equity_delivery_v1",
        "slippage_model": "fixed_bps_5",
        "execution": "NEXT_BAR_OPEN",
        "selection_criterion": "mean_validation_sharpe",
        "ranking_split": "validation",
        "test_policy": "sealed_until_finalists",
    }

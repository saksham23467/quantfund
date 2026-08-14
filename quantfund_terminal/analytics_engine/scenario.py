"""Scenario analysis: estimate portfolio PnL under factor/market shocks.

Two modes:
  1. Factor/market shock scenarios (parametric via exposures + market beta).
  2. Historical replay of the worst realized multi-day window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantfund_terminal.analytics_engine.attribution import exposure_matrix
from quantfund_terminal.analytics_engine.portfolio import (
    _portfolio_returns,
    normalize_holdings,
)

PRESET_SCENARIOS: dict[str, dict[str, float]] = {
    "gfc_2008_like":     {"market": -0.35, "low_vol": 0.10, "momentum": -0.15},
    "covid_2020_crash":  {"market": -0.30, "low_vol": 0.08, "size": -0.10},
    "rate_shock":        {"market": -0.08, "value": 0.06, "low_vol": -0.05},
    "momentum_crash":    {"market": -0.05, "momentum": -0.20, "value": 0.10},
    "melt_up":           {"market": 0.15, "momentum": 0.10, "size": 0.05},
}


def _market_beta(port_ret: pd.Series, market_ret: pd.Series) -> float:
    if port_ret.empty or market_ret.var() == 0:
        return 0.0
    return float(np.cov(port_ret, market_ret)[0, 1] / market_ret.var())


def scenario_analysis(
    holdings: list[dict],
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    *,
    custom: dict[str, dict[str, float]] | None = None,
    lookback: int = 126,
) -> dict:
    weights = normalize_holdings(holdings, prices)
    held = [s for s in weights if s in prices.columns]
    if not held:
        return {"error": "no held assets overlap the universe", "scenarios": []}

    w = pd.Series({s: weights[s] for s in held})
    w = w / w.abs().sum()

    B = exposure_matrix(prices, volumes, lookback=lookback)
    port_exposure = {f: float((w * B.loc[held, f]).sum()) for f in B.columns}

    returns = prices.pct_change().fillna(0.0)
    port_ret = _portfolio_returns(weights, returns)
    beta = _market_beta(port_ret, returns.mean(axis=1))

    def _pnl(shocks: dict[str, float]) -> float:
        pnl = beta * shocks.get("market", 0.0)
        for f, expo in port_exposure.items():
            if f in shocks:
                pnl += expo * shocks[f]
        return pnl

    scenarios = {**PRESET_SCENARIOS, **(custom or {})}
    results = [
        {
            "scenario": name,
            "shocks": shocks,
            "estimated_pnl": round(_pnl(shocks), 5),
        }
        for name, shocks in scenarios.items()
    ]
    results.sort(key=lambda r: r["estimated_pnl"])

    # Historical worst 5-day window replay.
    roll5 = (1 + port_ret).rolling(5).apply(lambda x: x.prod() - 1, raw=True).dropna()
    worst_5d = float(roll5.min()) if not roll5.empty else 0.0
    worst_date = roll5.idxmin().strftime("%Y-%m-%d") if not roll5.empty else None

    return {
        "portfolio_beta": round(beta, 4),
        "factor_exposures": {k: round(v, 4) for k, v in port_exposure.items()},
        "scenarios": results,
        "historical_worst_5d": {"return": round(worst_5d, 5), "ending": worst_date},
        "note": "Parametric PnL via market beta + factor exposures on the selected dataset.",
    }

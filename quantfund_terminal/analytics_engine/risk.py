"""Risk command-center analytics: exposure, leverage, vol, VaR, stress tests.

Read-only. These are analytical measures over a portfolio + price panel; they do
not connect to any broker and cannot move capital.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantfund_terminal.analytics_engine.portfolio import (
    _portfolio_returns,
    normalize_holdings,
)

STRESS_SCENARIOS = {
    "market_down_5pct": -0.05,
    "market_down_10pct": -0.10,
    "market_crash_20pct": -0.20,
}


def risk_snapshot(
    holdings: list[dict],
    prices: pd.DataFrame,
    *,
    sector_map: dict[str, str] | None = None,
) -> dict:
    sector_map = sector_map or {}
    weights = normalize_holdings(holdings, prices)
    returns = prices.pct_change().fillna(0.0)
    port_ret = _portfolio_returns(weights, returns)
    market_ret = returns.mean(axis=1)

    long_exp = sum(w for w in weights.values() if w > 0)
    short_exp = -sum(w for w in weights.values() if w < 0)
    gross = long_exp + short_exp
    net = long_exp - short_exp
    leverage = gross  # normalized weights => gross exposure is leverage proxy

    beta = 0.0
    if not port_ret.empty and market_ret.var() > 0:
        beta = float(np.cov(port_ret, market_ret)[0, 1] / market_ret.var())

    ann_vol = float(port_ret.std(ddof=1) * np.sqrt(252)) if not port_ret.empty else 0.0
    var95 = float(np.percentile(port_ret, 5)) if not port_ret.empty else 0.0

    sector_conc: dict[str, float] = {}
    for sym, w in weights.items():
        sec = sector_map.get(sym, "UNKNOWN")
        sector_conc[sec] = sector_conc.get(sec, 0.0) + w

    stress = {
        name: {
            "market_shock": shock,
            "estimated_portfolio_pnl": round(beta * shock, 5),
        }
        for name, shock in STRESS_SCENARIOS.items()
    }

    return {
        "gross_exposure": round(gross, 4),
        "net_exposure": round(net, 4),
        "long_exposure": round(long_exp, 4),
        "short_exposure": round(short_exp, 4),
        "leverage": round(leverage, 4),
        "beta": round(beta, 4),
        "annualized_volatility": round(ann_vol, 4),
        "var_95_daily": round(var95, 5),
        "largest_position": max(
            ({"symbol": s, "weight": round(w, 4)} for s, w in weights.items()),
            key=lambda d: abs(d["weight"]),
            default={"symbol": None, "weight": 0.0},
        ),
        "sector_concentration": {k: round(v, 4) for k, v in sector_conc.items()},
        "stress_tests": stress,
        "note": "Stress PnL estimated via portfolio beta to the demo market proxy.",
    }

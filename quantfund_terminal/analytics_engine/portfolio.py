"""Portfolio analytics: beta, VaR, exposures, drawdown, concentration, correlation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantfund_terminal.analytics_engine.metrics import max_drawdown


def normalize_holdings(holdings: list[dict], prices: pd.DataFrame | None = None) -> dict[str, float]:
    """Return weights that sum to 1 from either weights or quantity*price."""
    values: dict[str, float] = {}
    for h in holdings:
        sym = str(h["symbol"]).upper()
        if "weight" in h and h["weight"] is not None:
            values[sym] = values.get(sym, 0.0) + float(h["weight"])
        else:
            qty = float(h.get("quantity", 0.0))
            price = h.get("price")
            if price is None and prices is not None and sym in prices.columns:
                price = float(prices[sym].iloc[-1])
            values[sym] = values.get(sym, 0.0) + qty * float(price or 0.0)
    total = sum(abs(v) for v in values.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in values.items()}


def _portfolio_returns(weights: dict[str, float], returns: pd.DataFrame) -> pd.Series:
    cols = [s for s in weights if s in returns.columns]
    if not cols:
        return pd.Series(dtype=float)
    w = pd.Series({s: weights[s] for s in cols})
    return (returns[cols] * w).sum(axis=1)


def analyze_portfolio(
    holdings: list[dict],
    prices: pd.DataFrame,
    *,
    sector_map: dict[str, str] | None = None,
) -> dict:
    sector_map = sector_map or {}
    weights = normalize_holdings(holdings, prices)
    returns = prices.pct_change().fillna(0.0)
    port_ret = _portfolio_returns(weights, returns)
    market_ret = returns.mean(axis=1)  # equal-weight panel as market proxy

    # Beta vs market proxy.
    beta = 0.0
    if not port_ret.empty and market_ret.var() > 0:
        beta = float(np.cov(port_ret, market_ret)[0, 1] / market_ret.var())

    var95 = float(np.percentile(port_ret, 5)) if not port_ret.empty else 0.0
    var99 = float(np.percentile(port_ret, 1)) if not port_ret.empty else 0.0

    # Sector exposure.
    sector_exposure: dict[str, float] = {}
    for sym, w in weights.items():
        sec = sector_map.get(sym, "UNKNOWN")
        sector_exposure[sec] = sector_exposure.get(sec, 0.0) + w

    # Concentration.
    hhi = float(sum(w * w for w in weights.values()))
    top5 = sorted(weights.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]

    # Correlation among held names.
    held = [s for s in weights if s in returns.columns]
    corr = returns[held].corr().round(3).to_dict() if held else {}

    return {
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "beta_vs_market_proxy": round(beta, 4),
        "var_95_daily": round(var95, 5),
        "var_99_daily": round(var99, 5),
        "max_drawdown": round(max_drawdown(port_ret), 5) if not port_ret.empty else 0.0,
        "sector_exposure": {k: round(v, 4) for k, v in sector_exposure.items()},
        "concentration_hhi": round(hhi, 4),
        "top_holdings": [{"symbol": s, "weight": round(w, 4)} for s, w in top5],
        "correlation": corr,
        "note": "Beta uses an equal-weight panel proxy for the market on demo data.",
    }

"""Factor attribution: decompose portfolio return into factor + specific pieces.

Honest, demo-grade attribution on the selected dataset. On DEMO_SYNTHETIC data
value/quality exposures are proxies (see factors.PROXY_FACTORS).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantfund_terminal.analytics_engine.factors import (
    FACTORS,
    PROXY_FACTORS,
    factor_return_series,
    factor_scores,
)


def _zscore_last(scores: pd.DataFrame) -> pd.Series:
    row = scores.iloc[-1].dropna()
    if row.std(ddof=0) == 0 or row.empty:
        return row * 0.0
    return (row - row.mean()) / row.std(ddof=0)


def exposure_matrix(prices: pd.DataFrame, volumes: pd.DataFrame, *, lookback: int = 126) -> pd.DataFrame:
    """Assets x factors z-scored exposure matrix (latest cross-section)."""
    cols = {}
    for f in FACTORS:
        cols[f] = _zscore_last(factor_scores(prices, volumes, f, lookback=lookback))
    return pd.DataFrame(cols).fillna(0.0)


def factor_attribution(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    weights: dict[str, float],
    *,
    lookback: int = 126,
) -> dict:
    B = exposure_matrix(prices, volumes, lookback=lookback)
    held = [s for s in weights if s in B.index]
    if not held:
        return {"error": "no held assets overlap the universe", "contributions": []}
    w = pd.Series({s: weights[s] for s in held})
    w = w / w.abs().sum()

    port_exposure = {f: float((w * B.loc[held, f]).sum()) for f in FACTORS}

    contributions = []
    total_factor = 0.0
    for f in FACTORS:
        fr = factor_return_series(prices, volumes, f, lookback=lookback)
        ann = float((1 + fr).prod() ** (252 / max(1, len(fr))) - 1) if len(fr) else 0.0
        contrib = port_exposure[f] * ann
        total_factor += contrib
        contributions.append(
            {
                "factor": f,
                "is_proxy": f in PROXY_FACTORS,
                "exposure": round(port_exposure[f], 4),
                "factor_return_annualized": round(ann, 5),
                "contribution_annualized": round(contrib, 5),
            }
        )

    asset_returns = prices.pct_change().fillna(0.0)[held]
    port_ret = (asset_returns * w).sum(axis=1)
    port_ann = float((1 + port_ret).prod() ** (252 / max(1, len(port_ret))) - 1)
    specific = port_ann - total_factor

    return {
        "portfolio_return_annualized": round(port_ann, 5),
        "factor_contribution_total": round(total_factor, 5),
        "specific_return": round(specific, 5),
        "contributions": sorted(
            contributions, key=lambda c: abs(c["contribution_annualized"]), reverse=True
        ),
        "note": "Exposures are latest cross-sectional z-scores; value/quality are proxies on demo data.",
    }

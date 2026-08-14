"""Risk decomposition: marginal & component contributions to portfolio risk."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantfund_terminal.analytics_engine.portfolio import normalize_holdings


def risk_decomposition(holdings: list[dict], prices: pd.DataFrame) -> dict:
    weights = normalize_holdings(holdings, prices)
    held = [s for s in weights if s in prices.columns]
    if not held:
        return {"error": "no held assets overlap the universe", "contributions": []}

    w = np.array([weights[s] for s in held])
    returns = prices.pct_change().dropna()[held]
    cov = returns.cov().values * 252.0  # annualized covariance

    port_var = float(w @ cov @ w)
    port_vol = float(np.sqrt(max(port_var, 1e-18)))

    marginal = (cov @ w) / port_vol           # marginal contribution to risk
    component = w * marginal                   # component contribution (sums to vol)
    pct = component / port_vol if port_vol else np.zeros_like(component)

    contributions = sorted(
        (
            {
                "symbol": held[i],
                "weight": round(float(w[i]), 4),
                "marginal_risk": round(float(marginal[i]), 5),
                "component_risk": round(float(component[i]), 5),
                "pct_of_total_risk": round(float(pct[i]), 4),
            }
            for i in range(len(held))
        ),
        key=lambda d: d["component_risk"],
        reverse=True,
    )

    # Diversification ratio: weighted avg standalone vol / portfolio vol.
    standalone = np.sqrt(np.diag(cov))
    div_ratio = float((w @ standalone) / port_vol) if port_vol else 0.0

    return {
        "portfolio_volatility_annualized": round(port_vol, 5),
        "diversification_ratio": round(div_ratio, 4),
        "contributions": contributions,
        "top_risk_contributor": contributions[0] if contributions else None,
        "note": "Component risks sum to portfolio volatility (Euler decomposition).",
    }

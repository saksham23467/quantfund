"""Factor research utilities: scores, long-short returns, rolling Sharpe, corr."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantfund_terminal.analytics_engine.metrics import sharpe

FACTORS = ["momentum", "quality", "value", "low_vol", "size"]
# Factors requiring fundamentals we cannot certify on demo data are flagged proxy.
PROXY_FACTORS = {"quality", "value"}


def factor_scores(
    prices: pd.DataFrame, volumes: pd.DataFrame, factor: str, *, lookback: int = 126
) -> pd.DataFrame:
    rets = prices.pct_change()
    if factor == "momentum":
        return prices.pct_change(lookback)
    if factor == "low_vol":
        return -rets.rolling(lookback).std()
    if factor == "size":
        # Smaller traded value scores higher (classic size premium proxy).
        return -np.log((prices * volumes).clip(lower=1.0))
    if factor == "value":
        # PROXY: deterministic pseudo-book/price from inverse long-term price.
        return 1.0 / prices.rolling(lookback).mean()
    if factor == "quality":
        # PROXY: low drawdown + positive drift as a quality stand-in.
        drift = rets.rolling(lookback).mean()
        dd = rets.rolling(lookback).min()
        return drift - dd.abs()
    raise ValueError(f"unknown factor {factor!r}")


def factor_return_series(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    factor: str,
    *,
    lookback: int = 126,
    quantile: float = 0.2,
) -> pd.Series:
    """Long top-quantile / short bottom-quantile daily return series."""
    scores = factor_scores(prices, volumes, factor, lookback=lookback)
    fwd = prices.pct_change().shift(-1)  # next-day return
    out = {}
    for dt, row in scores.iterrows():
        r = row.dropna()
        if len(r) < 5:
            continue
        k = max(1, int(len(r) * quantile))
        longs = r.nlargest(k).index
        shorts = r.nsmallest(k).index
        f = fwd.loc[dt]
        out[dt] = float(f[longs].mean() - f[shorts].mean())
    return pd.Series(out).dropna()


def rolling_sharpe(returns: pd.Series, *, window: int = 126) -> pd.Series:
    def _s(x: pd.Series) -> float:
        if x.std(ddof=1) == 0:
            return 0.0
        return float(np.sqrt(252) * x.mean() / x.std(ddof=1))

    return returns.rolling(window).apply(_s, raw=False).dropna()


def factor_correlations(series_by_factor: dict[str, pd.Series]) -> pd.DataFrame:
    frame = pd.DataFrame(series_by_factor).dropna(how="all")
    return frame.corr().round(4)


def factor_panel_summary(
    prices: pd.DataFrame, volumes: pd.DataFrame, *, lookback: int = 126
) -> dict:
    series = {
        f: factor_return_series(prices, volumes, f, lookback=lookback) for f in FACTORS
    }
    corr = factor_correlations(series)
    out_factors = []
    for f, s in series.items():
        out_factors.append(
            {
                "factor": f,
                "is_proxy": f in PROXY_FACTORS,
                "annualized_return": round(float((1 + s).prod() ** (252 / max(1, len(s))) - 1), 5)
                if len(s)
                else 0.0,
                "sharpe": round(sharpe(s), 4),
                "cumulative": [
                    {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 5)}
                    for d, v in (1 + s).cumprod().items()
                ][:: max(1, len(s) // 250 or 1)],
            }
        )
    return {
        "factors": out_factors,
        "correlations": corr.to_dict(),
        "note": "value/quality are labelled proxies on demo data (no certified fundamentals).",
    }

"""Market Dashboard service — indices, sectors, breadth, movers, volatility.

Uses the shared synthetic demo panel (data_class=DEMO_SYNTHETIC, delayed
fallback). When a licensed/exchange real-time feed is connected, only this
service changes; the API contract stays identical.
"""

from __future__ import annotations

import numpy as np

from quantfund_terminal.analytics_engine.sample_data import SECTOR_MAP
from quantfund_terminal.backend.app.services.panel import get_panel

_BANKNIFTY = ["HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK"]


def _index_level(prices, cols):
    sub = prices[cols]
    norm = sub / sub.iloc[0]
    return norm.mean(axis=1) * 100.0  # equal-weight index, base=100


def get_market_snapshot() -> dict:
    panel = get_panel()
    prices = panel.prices
    rets = panel.returns
    as_of = prices.index[-1]
    last = rets.iloc[-1]

    nifty = _index_level(prices, list(prices.columns))
    banknifty = _index_level(prices, [c for c in _BANKNIFTY if c in prices.columns])

    def _idx_block(level_series, member_rets):
        chg_1d = float(member_rets.mean())
        vol_20 = float(level_series.pct_change().tail(20).std() * np.sqrt(252))
        return {
            "level": round(float(level_series.iloc[-1]), 2),
            "change_pct_1d": round(chg_1d * 100, 3),
            "annualized_vol_20d": round(vol_20 * 100, 2),
        }

    sector_perf: dict[str, float] = {}
    sector_counts: dict[str, int] = {}
    for sym in prices.columns:
        sec = SECTOR_MAP.get(sym, "UNKNOWN")
        sector_perf[sec] = sector_perf.get(sec, 0.0) + float(last[sym])
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
    sector_perf = {
        k: round(v / sector_counts[k] * 100, 3) for k, v in sector_perf.items()
    }

    movers = last.sort_values(ascending=False)
    top_gainers = [
        {"symbol": s, "change_pct": round(float(v) * 100, 3)}
        for s, v in movers.head(5).items()
    ]
    top_losers = [
        {"symbol": s, "change_pct": round(float(v) * 100, 3)}
        for s, v in movers.tail(5).items()
    ]

    advancers = int((last > 0).sum())
    decliners = int((last < 0).sum())

    return {
        "data_class": panel.data_class,
        "source": panel.source,
        "mode": "delayed_fallback",
        "as_of": as_of.strftime("%Y-%m-%d"),
        "indices": {
            "NIFTY50_PROXY": _idx_block(nifty, last),
            "BANKNIFTY_PROXY": _idx_block(
                banknifty, last[[c for c in _BANKNIFTY if c in last.index]]
            ),
        },
        "sector_performance": dict(sorted(sector_perf.items(), key=lambda kv: -kv[1])),
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "breadth": {
            "advancers": advancers,
            "decliners": decliners,
            "advance_decline_ratio": round(advancers / max(1, decliners), 3),
        },
        "volatility": {
            "nifty_proxy_annualized_20d": _idx_block(nifty, last)["annualized_vol_20d"]
        },
        "disclaimer": (
            "Synthetic demo data (DEMO_SYNTHETIC). Not exchange-authoritative and "
            "not certified; for UI demonstration only."
        ),
    }

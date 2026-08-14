"""Calendar-year diagnostic coverage — not used for strategy selection."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from quantfund.data.models import MarketBar


def annual_coverage(bars: list[MarketBar]) -> dict[str, Any]:
    by_year: dict[int, list[MarketBar]] = defaultdict(list)
    for b in bars:
        by_year[b.timestamp.year].append(b)
    years = {}
    for y in sorted(by_year):
        ys = sorted(by_year[y], key=lambda x: x.timestamp)
        rets = []
        for i in range(1, len(ys)):
            prev, cur = ys[i - 1].close, ys[i].close
            if prev > 0:
                rets.append(cur / prev - 1.0)
        ann_ret = None
        vol = None
        if ys:
            ann_ret = ys[-1].close / ys[0].close - 1.0
        if len(rets) >= 2:
            vol = float(np.std(rets, ddof=1) * np.sqrt(252))
        years[str(y)] = {
            "bars": len(ys),
            "start": ys[0].timestamp.date().isoformat(),
            "end": ys[-1].timestamp.date().isoformat(),
            "buy_hold_return": ann_ret,
            "realized_vol": vol,
        }
    return {"years": years, "year_list": list(years.keys())}


def strategy_annual_returns(
    bars: list[MarketBar],
    *,
    equity_curve: list[tuple[str, float]],
) -> dict[str, float | None]:
    """Map equity curve points to calendar-year returns (diagnostic)."""
    if not equity_curve:
        return {}
    # equity_curve: (iso timestamp, equity)
    by_year: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for ts, eq in equity_curve:
        year = int(ts[:4])
        by_year[year].append((ts, eq))
    out: dict[str, float | None] = {}
    for y, pts in sorted(by_year.items()):
        pts = sorted(pts)
        if len(pts) < 2 or pts[0][1] == 0:
            out[str(y)] = None
        else:
            out[str(y)] = pts[-1][1] / pts[0][1] - 1.0
    return out

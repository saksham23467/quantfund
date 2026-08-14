"""Explicit handling of bars outside the requested research window."""

from __future__ import annotations

from datetime import date
from typing import Any

from quantfund.data.models import MarketBar

# Phase 17B / 17C research request window
REQUESTED_START = date(2018, 1, 1)


def split_edge_bars(
    bars: list[MarketBar],
    *,
    requested_start: date = REQUESTED_START,
    requested_end: date | None = None,
) -> dict[str, Any]:
    """Separate in-window bars from pre/post edge bars. Does not invent data."""
    before: list[MarketBar] = []
    inside: list[MarketBar] = []
    after: list[MarketBar] = []
    for b in bars:
        d = b.timestamp.date()
        if d < requested_start:
            before.append(b)
        elif requested_end is not None and d > requested_end:
            after.append(b)
        else:
            inside.append(b)
    return {
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat() if requested_end else None,
        "edge_bars_before": [
            {"session_date": b.timestamp.date().isoformat(), "symbol": b.symbol}
            for b in before
        ],
        "edge_bars_after": [
            {"session_date": b.timestamp.date().isoformat(), "symbol": b.symbol}
            for b in after
        ],
        "edge_before_count": len(before),
        "edge_after_count": len(after),
        "in_window_count": len(inside),
        "policy": "exclude_edge_bars_from_certified_window",
        "note": (
            "Bars with session_date < requested_start (e.g. 2017-12-31 from "
            "timezone/API edge) are reported and excluded from the certified "
            "research window. RAW source package v1 is never mutated."
        ),
        "in_window_bars": inside,
        "before_bars": before,
        "after_bars": after,
    }

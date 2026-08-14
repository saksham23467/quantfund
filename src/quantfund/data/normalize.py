"""Normalization of raw bar records into MarketBar objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from quantfund.data.models import MarketBar
from quantfund.data.validate import sort_bars, validate_bars


def _to_datetime(value: Any) -> datetime:
    """Normalize bar timestamps to timezone-naive session datetimes.

    For tz-aware values, preserve the *local* calendar date in the timestamp's
    own timezone (e.g. Asia/Kolkata midnight stays that session date). Converting
    midnight IST → UTC previously shifted daily bars back one calendar day and
    broke NSE session alignment.
    """
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.to_pydatetime().replace(tzinfo=None)
    local = ts.tz_convert(ts.tz)
    return datetime(local.year, local.month, local.day)


def dataframe_to_bars(df: pd.DataFrame, *, symbol: str) -> list[MarketBar]:
    """Convert a normalized OHLCV DataFrame into MarketBar list.

    Expected columns: timestamp|date|Datetime, open, high, low, close, volume.
    """
    if df.empty:
        return []

    frame = df.copy()
    cols = {c.lower(): c for c in frame.columns}
    ts_col = None
    for candidate in ("timestamp", "date", "datetime", "datetime"):
        if candidate in cols:
            ts_col = cols[candidate]
            break
    if ts_col is None and isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.reset_index()
        cols = {c.lower(): c for c in frame.columns}
        for candidate in ("timestamp", "date", "datetime", "index"):
            if candidate in cols:
                ts_col = cols[candidate]
                break
    if ts_col is None:
        raise ValueError("DataFrame must include a timestamp/date column or DatetimeIndex")

    required = ("open", "high", "low", "close")
    for name in required:
        if name not in cols:
            raise ValueError(f"missing required column: {name}")

    volume_col = cols.get("volume")
    bars: list[MarketBar] = []
    for _, row in frame.iterrows():
        volume = float(row[volume_col]) if volume_col is not None else 0.0
        bars.append(
            MarketBar(
                timestamp=_to_datetime(row[ts_col]),
                symbol=symbol,
                open=float(row[cols["open"]]),
                high=float(row[cols["high"]]),
                low=float(row[cols["low"]]),
                close=float(row[cols["close"]]),
                volume=volume,
            )
        )
    return validate_bars(sort_bars(bars), require_non_empty=False)


def bars_to_dataframe(bars: list[MarketBar]) -> pd.DataFrame:
    """Convert MarketBar list to a normalized DataFrame."""
    records = [
        {
            "timestamp": b.timestamp,
            "symbol": b.symbol,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in bars
    ]
    if not records:
        return pd.DataFrame(
            columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"]
        )
    return pd.DataFrame.from_records(records)

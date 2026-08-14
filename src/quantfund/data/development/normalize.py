"""Normalize free/public OHLCV into project MarketBar representation.

Does not forward-fill OHLC, invent volume, or silently repair bars.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quantfund.data.models import Instrument, MarketBar
from quantfund.data.normalize import dataframe_to_bars


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    # Common NSE bhavcopy / Yahoo aliases
    rename = {
        "SYMBOL": "symbol",
        "Symbol": "symbol",
        "TIMESTAMP": "timestamp",
        "Date": "timestamp",
        "DATE": "timestamp",
        "OPEN": "open",
        "HIGH": "high",
        "LOW": "low",
        "CLOSE": "close",
        "TOTTRDQTY": "volume",
        "VOLUME": "volume",
        "Volume": "volume",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
    }
    frame = frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns})
    cols = {c.lower(): c for c in frame.columns}
    # Lowercase standardize
    out = pd.DataFrame()
    for name in ("timestamp", "date", "datetime"):
        if name in cols:
            out["timestamp"] = frame[cols[name]]
            break
    for name in ("open", "high", "low", "close", "volume", "symbol"):
        if name in cols:
            out[name] = frame[cols[name]]
    return out


def load_ohlcv_csv(path: Path, *, default_symbol: str | None = None) -> list[MarketBar]:
    """Load a single-symbol or multi-symbol OHLCV CSV. No fabrication."""
    path = Path(path)
    df = pd.read_csv(path)
    norm = _normalize_columns(df)
    if norm.empty:
        return []
    if "symbol" in norm.columns:
        bars: list[MarketBar] = []
        for sym, grp in norm.groupby("symbol"):
            symbol = str(sym).replace(".NS", "").replace(".NSE", "")
            bars.extend(dataframe_to_bars(grp.drop(columns=["symbol"]), symbol=symbol))
        return bars
    if not default_symbol:
        # Infer from filename
        default_symbol = path.stem.replace(".NS", "").upper()
    return dataframe_to_bars(norm, symbol=default_symbol)


def load_bars_directory(root: Path) -> list[MarketBar]:
    """Load bars/*.csv (one symbol per file)."""
    root = Path(root)
    bars_dir = root / "bars" if (root / "bars").is_dir() else root
    bars: list[MarketBar] = []
    for path in sorted(bars_dir.glob("*.csv")):
        bars.extend(load_ohlcv_csv(path, default_symbol=path.stem.replace(".NS", "")))
    return bars


def instruments_from_bars(bars: list[MarketBar]) -> list[Instrument]:
    symbols = sorted({b.symbol for b in bars})
    return [
        Instrument(
            symbol=s,
            instrument_id=f"NSE:{s}",
            exchange="NSE",
            currency="INR",
        )
        for s in symbols
    ]


def bars_summary(bars: list[MarketBar]) -> dict[str, Any]:
    if not bars:
        return {
            "bar_count": 0,
            "instrument_count": 0,
            "date_coverage_start": None,
            "date_coverage_end": None,
        }
    dates = [b.timestamp.date() for b in bars]
    return {
        "bar_count": len(bars),
        "instrument_count": len({b.symbol for b in bars}),
        "date_coverage_start": min(dates).isoformat(),
        "date_coverage_end": max(dates).isoformat(),
    }

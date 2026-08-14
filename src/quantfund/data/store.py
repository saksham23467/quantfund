"""Parquet storage for normalized market bars.

Pipeline: raw source → raw files (immutable) → validation → normalization → Parquet.
Processed Parquet must be reproducible from raw inputs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from quantfund.data.models import MarketBar
from quantfund.data.normalize import bars_to_dataframe, dataframe_to_bars
from quantfund.data.validate import validate_bars


def save_bars_parquet(
    bars: list[MarketBar],
    path: Path,
    *,
    data_source: str,
    data_version: str,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Persist validated bars to Parquet and a sidecar metadata JSON."""
    validated = validate_bars(bars, require_non_empty=True)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    df = bars_to_dataframe(validated)
    df.to_parquet(path, index=False)

    meta = {
        "data_source": data_source,
        "data_version": data_version,
        "symbol_count": len({b.symbol for b in validated}),
        "bar_count": len(validated),
        "start": validated[0].timestamp.isoformat(),
        "end": validated[-1].timestamp.isoformat(),
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
        "extra": metadata or {},
    }
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def load_bars_parquet(path: Path, *, symbol: str | None = None) -> list[MarketBar]:
    """Load bars from Parquet and re-validate."""
    path = Path(path)
    df = pd.read_parquet(path)
    if symbol is not None:
        if "symbol" in df.columns:
            df = df[df["symbol"] == symbol]
        bars = dataframe_to_bars(df, symbol=symbol)
    else:
        if "symbol" not in df.columns:
            raise ValueError("Parquet missing symbol column; pass symbol= explicitly")
        bars: list[MarketBar] = []
        for sym, group in df.groupby("symbol", sort=False):
            bars.extend(dataframe_to_bars(group, symbol=str(sym)))
        bars = sorted(bars, key=lambda b: (b.timestamp, b.symbol))
    return validate_bars(bars, require_non_empty=False)


def read_parquet_metadata(path: Path) -> dict[str, Any]:
    """Read sidecar metadata written by ``save_bars_parquet``."""
    meta_path = Path(path).with_suffix(Path(path).suffix + ".meta.json")
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))

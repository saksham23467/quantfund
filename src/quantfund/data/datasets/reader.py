"""Dataset reader with as-of API that cannot expose future bars."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from quantfund.data.datasets.manifest import DatasetManifest
from quantfund.data.models import MarketBar
from quantfund.data.normalize import dataframe_to_bars
from quantfund.data.validate import validate_bars


class FutureDataError(RuntimeError):
    """Raised when a caller requests or would receive bars after as-of time."""


class DatasetReader:
    """Read symbol-partitioned daily datasets with chronology safety."""

    def __init__(self, dataset_root: Path) -> None:
        self.root = Path(dataset_root)
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest.json missing in {self.root}")
        self.manifest = DatasetManifest.model_validate(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )

    @classmethod
    def open(cls, datasets_root: Path, dataset_id: str, dataset_version: str) -> DatasetReader:
        return cls(Path(datasets_root) / dataset_id / dataset_version)

    def symbols(self) -> list[str]:
        bars_root = self.root / "bars"
        if not bars_root.exists():
            return []
        out = []
        for p in sorted(bars_root.glob("symbol=*")):
            out.append(p.name.split("=", 1)[1])
        return out

    def _load_symbol_frame(self, symbol: str) -> pd.DataFrame:
        path = self.root / "bars" / f"symbol={symbol}" / "part.parquet"
        if not path.exists():
            raise FileNotFoundError(f"No bars for symbol={symbol} at {path}")
        return pd.read_parquet(path)

    def get_history(
        self,
        symbol: str,
        *,
        start: datetime | date | None = None,
        end: datetime | date | None = None,
        as_of: datetime | date | None = None,
        price_field: str = "raw",
    ) -> list[MarketBar]:
        """Return bars for symbol with optional as-of cutoff.

        ``as_of`` ensures no bar with timestamp > as_of is returned.
        ``price_field``:
          - raw: MarketBar uses RAW OHLC (execution default)
          - adjusted: MarketBar OHLC replaced with adj_* for research continuity
            (RAW columns remain in parquet; this only affects returned objects)
        """
        df = self._load_symbol_frame(symbol)
        if df.empty:
            return []

        ts = pd.to_datetime(df["timestamp"])
        mask = pd.Series(True, index=df.index)
        if start is not None:
            mask &= ts >= pd.Timestamp(start)
        if end is not None:
            mask &= ts <= pd.Timestamp(end)
        if as_of is not None:
            mask &= ts <= pd.Timestamp(as_of)

        sliced = df.loc[mask].copy()
        if as_of is not None and len(sliced) and pd.to_datetime(sliced["timestamp"]).max() > pd.Timestamp(as_of):
            raise FutureDataError("as-of reader produced future bars")

        if price_field == "adjusted":
            for col in ("open", "high", "low", "close"):
                adj = f"adj_{col}"
                if adj not in sliced.columns:
                    raise ValueError(f"missing {adj} in dataset")
                sliced[col] = sliced[adj]
        elif price_field != "raw":
            raise ValueError("price_field must be 'raw' or 'adjusted'")

        bars = dataframe_to_bars(sliced, symbol=symbol)
        bars = validate_bars(bars, require_non_empty=False)
        if as_of is not None:
            as_of_ts = pd.Timestamp(as_of).to_pydatetime()
            for bar in bars:
                if bar.timestamp > as_of_ts:
                    raise FutureDataError(
                        f"future bar {bar.timestamp.isoformat()} > as_of {as_of}"
                    )
        return bars

    def load_dividends(self) -> list[dict]:
        path = self.root / "dividends.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

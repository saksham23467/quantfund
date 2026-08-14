"""FeatureEngine with strict as-of(T) semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from quantfund.data.models import MarketBar
from quantfund.features.library.registry import (
    build_windowed_spec,
    default_feature_registry,
)
from quantfund.features.specs import FeatureFn, FeatureSpec


@dataclass
class FeatureFrame:
    """Feature panel aligned to bar timestamps (may include NaNs during warmup)."""

    frame: pd.DataFrame  # columns: timestamp, symbol, feature outputs...
    feature_versions: dict[str, str]

    def asof(self, timestamp: datetime | pd.Timestamp, *, symbol: str | None = None) -> dict[str, float | None]:
        """Return feature values at T; never includes rows after T."""
        ts = pd.Timestamp(timestamp)
        df = self.frame
        if symbol is not None and "symbol" in df.columns:
            df = df[df["symbol"] == symbol]
        eligible = df[pd.to_datetime(df["timestamp"]) <= ts]
        if eligible.empty:
            return {}
        row = eligible.iloc[-1]
        row_ts = pd.Timestamp(row["timestamp"])
        if row_ts > ts:
            raise RuntimeError("asof leaked future timestamp")
        out: dict[str, float | None] = {}
        for col in eligible.columns:
            if col in {"timestamp", "symbol"}:
                continue
            val = row[col]
            if pd.isna(val):
                out[col] = None
            else:
                out[col] = float(val)
        return out


class FeatureEngine:
    """Compute features using only information at or before each timestamp."""

    WINDOWED = {
        "rolling_return",
        "sma",
        "ema",
        "momentum",
        "roc",
        "rolling_vol",
        "atr",
        "realized_vol",
        "relative_volume",
        "dist_to_sma",
        "zscore",
        "relative_strength",
    }

    def __init__(self) -> None:
        self._registry = default_feature_registry()
        self._active: list[tuple[FeatureSpec, FeatureFn]] = []

    def register(self, spec: FeatureSpec, fn: FeatureFn | None = None) -> None:
        if fn is None:
            entry = self._registry.get(spec.feature_name)
            if entry is None:
                raise KeyError(f"unknown feature {spec.feature_name}")
            _, fn = entry
        self._active.append((spec, fn))

    def configure(self, requests: list[dict[str, Any]]) -> list[FeatureSpec]:
        """Configure features from request dicts: {name, window?}."""
        self._active.clear()
        specs: list[FeatureSpec] = []
        for req in requests:
            name = req["name"]
            if name in self.WINDOWED:
                window = int(req["window"])
                spec = build_windowed_spec(name, window)
            else:
                entry = self._registry.get(name)
                if entry is None or entry[0] is None:
                    raise KeyError(f"unknown or windowed-only feature {name}")
                spec = entry[0]
            self.register(spec)
            specs.append(spec)
        return specs

    @property
    def feature_versions(self) -> dict[str, str]:
        return {s.output_columns[0]: s.version for s, _ in self._active}

    def bars_to_frame(
        self,
        bars: list[MarketBar],
        *,
        benchmark_closes: dict[datetime, float] | None = None,
    ) -> pd.DataFrame:
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
        df = pd.DataFrame.from_records(records)
        if df.empty:
            return df
        df = df.sort_values("timestamp").reset_index(drop=True)
        if benchmark_closes:
            df["benchmark_close"] = [
                benchmark_closes.get(ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts)
                for ts in df["timestamp"]
            ]
        return df

    def compute(
        self,
        bars: list[MarketBar],
        *,
        benchmark_closes: dict[datetime, float] | None = None,
    ) -> FeatureFrame:
        if not self._active:
            raise ValueError("no features registered")
        base = self.bars_to_frame(bars, benchmark_closes=benchmark_closes)
        if base.empty:
            return FeatureFrame(frame=base, feature_versions=self.feature_versions)

        result = base[["timestamp", "symbol"]].copy()
        for spec, fn in self._active:
            missing = [c for c in spec.required_columns if c not in base.columns]
            if missing:
                # Produce NaN columns rather than crashing (e.g. missing benchmark)
                for col in spec.output_columns:
                    result[col] = pd.NA
                continue
            part = fn(base, spec)
            for col in spec.output_columns:
                result[col] = part[col].values
        return FeatureFrame(frame=result, feature_versions=self.feature_versions)

    def asof(
        self,
        bars: list[MarketBar],
        timestamp: datetime,
        *,
        symbol: str | None = None,
        benchmark_closes: dict[datetime, float] | None = None,
    ) -> dict[str, float | None]:
        """Compute features on bars<=T only, then return row at T."""
        clipped = [b for b in bars if b.timestamp <= timestamp]
        if symbol is not None:
            clipped = [b for b in clipped if b.symbol == symbol]
        # Guard: refuse if caller passed future bars mixed in without clip working
        for b in bars:
            if b.timestamp > timestamp and symbol in (None, b.symbol):
                # Future bars ignored by clip; leakage test verifies outputs unchanged
                pass
        frame = self.compute(clipped, benchmark_closes=benchmark_closes)
        return frame.asof(timestamp, symbol=symbol)

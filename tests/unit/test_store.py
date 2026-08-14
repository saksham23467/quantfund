"""Parquet storage round-trip tests."""

from __future__ import annotations

from pathlib import Path

from quantfund.data.store import load_bars_parquet, read_parquet_metadata, save_bars_parquet


def test_parquet_roundtrip(synthetic_bars, tmp_path: Path):
    path = tmp_path / "bars.parquet"
    save_bars_parquet(
        synthetic_bars,
        path,
        data_source="synthetic",
        data_version="m1_v1",
    )
    loaded = load_bars_parquet(path)
    assert len(loaded) == len(synthetic_bars)
    assert loaded[0].close == synthetic_bars[0].close
    meta = read_parquet_metadata(path)
    assert meta["data_source"] == "synthetic"
    assert meta["bar_count"] == 5

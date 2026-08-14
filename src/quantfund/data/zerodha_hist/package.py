"""Immutable Zerodha historical dataset packages — never overwrite versions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from quantfund.config import PATHS
from quantfund.data.ingest.checksums import hash_json
from quantfund.data.models import MarketBar
from quantfund.data.normalize import bars_to_dataframe
from quantfund.phase15.models import scrub_secrets


def research_zerodha_root() -> Path:
    root = PATHS.data_dir / "research" / "zerodha"
    root.mkdir(parents=True, exist_ok=True)
    return root


def next_dataset_version(dataset_id: str) -> str:
    base = research_zerodha_root() / dataset_id
    if not base.exists():
        return "v1"
    existing = sorted(
        p.name for p in base.iterdir() if p.is_dir() and p.name.startswith("v")
    )
    if not existing:
        return "v1"
    nums = []
    for name in existing:
        try:
            nums.append(int(name[1:]))
        except ValueError:
            continue
    return f"v{(max(nums) if nums else 0) + 1}"


def write_zerodha_dataset_package(
    *,
    bars: list[MarketBar],
    provenance: dict[str, Any],
    quality_report: dict[str, Any],
    corporate_actions: list[dict[str, Any]] | None = None,
    instrument_metadata: dict[str, Any] | None = None,
    dataset_id: str | None = None,
    version: str | None = None,
) -> Path:
    """Write immutable package. Refuses to overwrite an existing version dir."""
    if not bars:
        raise ValueError("empty_bars")
    symbols = sorted({b.symbol for b in bars})
    start = min(b.timestamp for b in bars).date().isoformat()
    end = max(b.timestamp for b in bars).date().isoformat()
    ds_id = dataset_id or f"zerodha_nse_daily_{start}_{end}".replace("-", "")
    ver = version or next_dataset_version(ds_id)
    out = research_zerodha_root() / ds_id / ver
    if out.exists():
        raise FileExistsError(f"dataset_immutable_refuse_overwrite:{out}")
    out.mkdir(parents=True)

    # bars.parquet
    df = bars_to_dataframe(bars)
    df.to_parquet(out / "bars.parquet", index=False)

    prov = scrub_secrets(dict(provenance))
    (out / "provenance.json").write_text(
        json.dumps(prov, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (out / "quality_report.json").write_text(
        json.dumps(scrub_secrets(quality_report), indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    ca = corporate_actions or []
    (out / "corporate_actions.json").write_text(
        json.dumps(ca, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    meta = scrub_secrets(instrument_metadata or {})
    (out / "instrument_metadata.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    manifest = scrub_secrets(
        {
            "dataset_id": ds_id,
            "dataset_version": ver,
            "provider": "zerodha",
            "source": "zerodha_historical_api",
            "source_grade": "non_exchange",
            "research_eligible": False,
            "eligibility": "DEVELOPMENT_ONLY",
            "price_policy": prov.get("price_policy", "unknown"),
            "interval": "1day",
            "exchange": "NSE",
            "symbols": symbols,
            "rows": len(bars),
            "start": start,
            "end": end,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "bars_file": "bars.parquet",
            "content_hash": hash_json(
                {
                    "rows": len(bars),
                    "symbols": symbols,
                    "start": start,
                    "end": end,
                    "ohlc_checksum": hash_json(
                        df[["timestamp", "symbol", "open", "high", "low", "close", "volume"]]
                        .astype(str)
                        .to_dict(orient="list")
                    ),
                }
            ),
        }
    )
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out


def load_bars_from_package(package_dir: Path) -> list[MarketBar]:
    from quantfund.data.normalize import dataframe_to_bars

    df = pd.read_parquet(package_dir / "bars.parquet")
    out: list[MarketBar] = []
    if "symbol" not in df.columns:
        raise ValueError("bars.parquet missing symbol column")
    for sym, part in df.groupby("symbol"):
        out.extend(dataframe_to_bars(part, symbol=str(sym)))
    return sorted(out, key=lambda b: (b.symbol, b.timestamp))

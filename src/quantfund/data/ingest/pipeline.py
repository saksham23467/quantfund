"""Raw ingest: write immutable download bundles with manifests and checksums."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from quantfund.data.ingest.checksums import directory_checksum, write_checksums
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.normalize import bars_to_dataframe
from quantfund.data.providers.base import DataProvider
from quantfund.data.providers.provenance import ProvenanceRecord
from quantfund.data.providers.roles import GradedDataProvider, ResearchProvider


@dataclass
class RawIngestResult:
    download_id: str
    source: str
    root: Path
    checksum: str
    symbols: list[str]
    bar_count: int
    downloaded_at: datetime
    provenance: ProvenanceRecord | None = None


def _source_grade_label(provider: DataProvider) -> str:
    if isinstance(provider, GradedDataProvider):
        return provider.source_grade.value
    if provider.name == "yfinance":
        return "non_exchange"
    return "unknown"


def ingest_bars_raw(
    *,
    provider: DataProvider,
    instruments: list[Instrument],
    raw_root: Path,
    start: datetime | None = None,
    end: datetime | None = None,
    download_id: str | None = None,
    extra_meta: dict | None = None,
) -> RawIngestResult:
    """Fetch history and persist an immutable RAW download bundle.

    Never modifies an existing download_id directory if it already exists.
    """
    download_id = download_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    root = Path(raw_root) / provider.name / download_id
    if root.exists():
        raise FileExistsError(
            f"Raw download directory already exists and is immutable: {root}"
        )
    bars_dir = root / "bars"
    bars_dir.mkdir(parents=True, exist_ok=False)

    all_bars: list[MarketBar] = []
    for instrument in instruments:
        bars = provider.get_history(instrument.symbol, start=start, end=end)
        df = bars_to_dataframe(bars)
        out = bars_dir / f"{instrument.symbol}.csv"
        df.to_csv(out, index=False)
        all_bars.extend(bars)

    instruments_path = root / "instruments.json"
    instruments_path.write_text(
        json.dumps([i.model_dump(mode="json") for i in instruments], indent=2),
        encoding="utf-8",
    )

    # Corporate actions / delisted when ResearchProvider
    if isinstance(provider, ResearchProvider):
        actions = provider.get_corporate_actions()
        (root / "corporate_actions.json").write_text(
            json.dumps([a.model_dump(mode="json") for a in actions], indent=2),
            encoding="utf-8",
        )
        delisted = provider.get_delisted_instruments()
        (root / "delisted_instruments.json").write_text(
            json.dumps([i.model_dump(mode="json") for i in delisted], indent=2),
            encoding="utf-8",
        )
        caps = provider.capabilities()
        (root / "capabilities.json").write_text(
            json.dumps(caps.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    downloaded_at = datetime.now(timezone.utc)
    checksum_path = write_checksums(root, label="raw")
    content_hash = directory_checksum(root)

    caps_dict = None
    if isinstance(provider, GradedDataProvider):
        caps_dict = provider.capabilities().model_dump(mode="json")

    limitations: list[str] = []
    if isinstance(provider, GradedDataProvider):
        limitations = list(provider.capabilities().limitations)

    provenance = ProvenanceRecord(
        source=provider.name,
        provider=provider.name,
        download_timestamp=downloaded_at,
        request_parameters={
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "symbols": [i.symbol for i in instruments],
            "instrument_ids": [i.instrument_id for i in instruments],
        },
        source_identifiers={
            "download_id": download_id,
            **{
                (i.instrument_id or i.symbol): (i.provider_symbol or i.symbol)
                for i in instruments
            },
        },
        content_hashes={"raw_bundle": content_hash},
        coverage={
            "bar_count": len(all_bars),
            "symbol_count": len(instruments),
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        limitations=limitations,
        license_ref=(extra_meta or {}).get("license_ref"),
        package_id=(extra_meta or {}).get("package_id"),
        package_version=(extra_meta or {}).get("package_version"),
        extras={"capabilities": caps_dict, **(extra_meta or {})},
    )
    (root / "provenance.json").write_text(
        json.dumps(provenance.to_manifest_dict(), indent=2),
        encoding="utf-8",
    )

    manifest = {
        "download_id": download_id,
        "source": provider.name,
        "provider": provider.name,
        "source_grade": _source_grade_label(provider),
        "downloaded_at": downloaded_at.isoformat(),
        "download_timestamp": downloaded_at.isoformat(),
        "request_parameters": provenance.request_parameters,
        "source_identifiers": provenance.source_identifiers,
        "content_hashes": provenance.content_hashes,
        "coverage": provenance.coverage,
        "limitations": limitations,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "symbols": [i.symbol for i in instruments],
        "bar_count": len(all_bars),
        "extra": extra_meta or {},
        "immutable": True,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Refresh checksums after writing provenance/manifest
    write_checksums(root, label="raw")
    checksum = directory_checksum(root)

    return RawIngestResult(
        download_id=download_id,
        source=provider.name,
        root=root,
        checksum=checksum,
        symbols=[i.symbol for i in instruments],
        bar_count=len(all_bars),
        downloaded_at=downloaded_at,
        provenance=provenance,
    )


def load_raw_bars(raw_download_root: Path) -> list[MarketBar]:
    """Load bars from an immutable raw download bundle."""
    from quantfund.data.normalize import dataframe_to_bars
    from quantfund.data.validate import validate_bars

    bars_dir = Path(raw_download_root) / "bars"
    bars: list[MarketBar] = []
    for csv_path in sorted(bars_dir.glob("*.csv")):
        df = pd.read_csv(csv_path, parse_dates=["timestamp"])
        symbol = csv_path.stem
        if "symbol" in df.columns and len(df):
            symbol = str(df["symbol"].iloc[0])
        bars.extend(dataframe_to_bars(df, symbol=symbol))
    return validate_bars(bars, require_non_empty=False)

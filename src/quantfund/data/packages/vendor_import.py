"""Vendor-neutral import helpers: normalize files into research package layout.

Vendor-specific parsing stays here (or in scripts). Never couples BacktestEngine,
ResearchRunner, StrategySpec, FeatureEngine, or eligibility to a vendor SDK.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.data.ingest.checksums import directory_checksum, hash_json
from quantfund.data.packages.contract import SCHEMA_VERSION


def deterministic_package_identity(
    *,
    package_id: str,
    package_version: str,
    content_hash: str,
) -> str:
    """Stable identity string from declared id/version + content hash."""
    return hash_json(
        {
            "package_id": package_id,
            "package_version": package_version,
            "content_hash": content_hash,
        }
    )


def write_package_json(
    package_root: Path,
    *,
    package_id: str,
    package_version: str,
    provider: str,
    source_grade: str,
    license_status: str,
    exchange_authority: bool = False,
    synthetic: bool = False,
    coverage_start: str | None = None,
    coverage_end: str | None = None,
    capabilities: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    extras: dict[str, Any] | None = None,
) -> Path:
    """Write a contract-conformant package.json (never includes eligibility claims)."""
    if source_grade in {"synthetic", "non_exchange"} and exchange_authority:
        raise ValueError("exchange_authority forbidden for synthetic/non_exchange")
    root = Path(package_root)
    root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "package_id": package_id,
        "package_version": package_version,
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "source_grade": source_grade,
        "license_status": license_status,
        "exchange_authority": bool(exchange_authority),
        "synthetic": bool(synthetic),
        "acquisition_timestamp": datetime.now(timezone.utc).isoformat(),
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "frequencies": ["1d"],
        "exchanges": ["NSE"],
        "capabilities": {
            "supports_daily_bars": True,
            "supports_instrument_master": True,
            "supports_corporate_actions": True,
            "supports_pit_universe": True,
            "supports_delisted_instruments": True,
            "supports_historical_identifiers": True,
            "supports_provenance": True,
            "supports_licensing_evidence": True,
            **(capabilities or {}),
        },
        "provenance": {
            "download_timestamp": datetime.now(timezone.utc).isoformat(),
            **(provenance or {}),
        },
    }
    if extras:
        for k, v in extras.items():
            if k in {
                "research_eligible",
                "research_eligibility",
                "eligibility",
                "accepted",
            }:
                raise ValueError(f"forbidden eligibility claim key: {k}")
            payload[k] = v
    path = root / "package.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def materialize_research_package(
    output_root: Path,
    *,
    package_id: str,
    package_version: str,
    provider: str,
    source_grade: str,
    license_status: str,
    instruments: list[dict[str, Any]],
    bars_by_symbol: dict[str, Path],
    corporate_actions: list[dict[str, Any]] | None = None,
    terminal_events: list[dict[str, Any]] | None = None,
    membership_file: Path | None = None,
    exchange_authority: bool = False,
    synthetic: bool = False,
    write_checksums: bool = True,
) -> dict[str, Any]:
    """Assemble a vendor-neutral package directory from already-normalized payloads."""
    root = Path(output_root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    (root / "instruments.json").write_text(
        json.dumps(instruments, indent=2, default=str), encoding="utf-8"
    )
    bars_dir = root / "bars"
    bars_dir.mkdir()
    for symbol, src in bars_by_symbol.items():
        shutil.copy(Path(src), bars_dir / f"{symbol}.csv")

    if corporate_actions is not None:
        (root / "corporate_actions.json").write_text(
            json.dumps(corporate_actions, indent=2, default=str), encoding="utf-8"
        )
    if terminal_events is not None:
        (root / "terminal_events.json").write_text(
            json.dumps(terminal_events, indent=2, default=str), encoding="utf-8"
        )
    if membership_file is not None:
        uni = root / "universe"
        uni.mkdir()
        src = Path(membership_file)
        # Always normalize to membership.json|csv so discovery finds it
        dest_name = (
            "membership.json" if src.suffix.lower() == ".json" else "membership.csv"
        )
        shutil.copy(src, uni / dest_name)

    dates: list[str] = []
    for inst in instruments:
        if inst.get("listing_date"):
            dates.append(str(inst["listing_date"])[:10])
    write_package_json(
        root,
        package_id=package_id,
        package_version=package_version,
        provider=provider,
        source_grade=source_grade,
        license_status=license_status,
        exchange_authority=exchange_authority,
        synthetic=synthetic,
        coverage_start=min(dates) if dates else None,
    )

    from quantfund.data.ingest.checksums import write_checksums

    content_hash = directory_checksum(root)
    if write_checksums:
        write_checksums(root, label="package")
        content_hash = directory_checksum(root)

    identity = deterministic_package_identity(
        package_id=package_id,
        package_version=package_version,
        content_hash=content_hash,
    )
    return {
        "package_root": str(root),
        "content_hash": content_hash,
        "package_identity": identity,
    }

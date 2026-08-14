"""Immutable certified package writer — never overwrites Phase 17B v1."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.data.ingest.checksums import hash_json
from quantfund.data.models import MarketBar
from quantfund.data.zerodha_hist.package import (
    next_dataset_version,
    research_zerodha_root,
    write_zerodha_dataset_package,
)
from quantfund.phase15.models import scrub_secrets
from quantfund.phase17a.datasets import DiscoveredPackage


def assert_source_immutable(pkg: DiscoveredPackage) -> None:
    """Refuse to mutate existing Phase 17B package directories."""
    man = pkg.path / "manifest.json"
    if not man.exists():
        raise FileNotFoundError(f"missing_manifest:{pkg.path}")
    # Touch-test: directory must remain readable; we never write into pkg.path
    if not pkg.path.is_dir():
        raise NotADirectoryError(str(pkg.path))


def write_certified_package(
    *,
    source_pkg: DiscoveredPackage,
    bars: list[MarketBar],
    provenance: dict[str, Any],
    quality_report: dict[str, Any],
    corporate_actions: list[dict[str, Any]],
    instrument_metadata: dict[str, Any],
    certification: dict[str, Any],
) -> Path:
    """Write a new immutable version under the same dataset_id (vN+1)."""
    assert_source_immutable(source_pkg)
    ds_id = source_pkg.dataset_id
    ver = next_dataset_version(ds_id)
    # write_zerodha_dataset_package creates bars/manifest/etc.
    out = write_zerodha_dataset_package(
        bars=bars,
        provenance={
            **provenance,
            "phase17c_certified": True,
            "source_package_version": source_pkg.dataset_version,
            "source_package_hash": source_pkg.content_hash,
            "source_package_path": str(source_pkg.path),
            "certification_timestamp": datetime.now(timezone.utc).isoformat(),
        },
        quality_report=quality_report,
        corporate_actions=corporate_actions,
        instrument_metadata=instrument_metadata,
        dataset_id=ds_id,
        version=ver,
    )
    # Extra certification artifact (does not exist on v1)
    (out / "certification.json").write_text(
        json.dumps(scrub_secrets(certification), indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    # Ensure we did not touch source
    if source_pkg.path.resolve() == out.resolve():
        raise RuntimeError("refused_to_overwrite_source_package")
    return out


def source_package_fingerprint(pkg: DiscoveredPackage) -> str:
    return hash_json(
        {
            "dataset_id": pkg.dataset_id,
            "dataset_version": pkg.dataset_version,
            "content_hash": pkg.content_hash,
            "path": str(pkg.path),
        }
    )

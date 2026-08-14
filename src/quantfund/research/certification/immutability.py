"""Immutable certified-package writer + verifier.

A certified package directory contains exactly:
  manifest.json, package.json, provenance.json, checksums.json, certification.json
Once written it must not be modified; a new dataset_version is required for any
change (overwrite is refused).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from quantfund.config import PATHS
from quantfund.research.certification.dataset_certification import DatasetCertification
from quantfund.research.data_contract.models import ResearchDatasetPackage


def certified_root() -> Path:
    root = PATHS.data_dir / "research" / "certified"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _aggregate_provenance(package: ResearchDatasetPackage) -> dict[str, Any]:
    prov: dict[str, dict[str, Any]] = {}
    collections = {
        "ohlcv": package.ohlcv,
        "identity": package.identity,
        "membership": package.membership,
        "delistings": package.delistings,
        "calendar": package.calendar,
        "corporate_actions": package.corporate_actions,
    }
    for name, records in collections.items():
        sources: dict[str, int] = {}
        for rec in records:
            key = f"{rec.provenance.source_name}|{rec.provenance.source_type.value}|{rec.provenance.source_license}"
            sources[key] = sources.get(key, 0) + 1
        prov[name] = {"record_count": len(records), "sources": sources}
    return prov


def write_certified_package(
    package: ResearchDatasetPackage,
    certification: DatasetCertification,
    *,
    root: Path | None = None,
) -> Path:
    m = package.manifest
    base = (root or certified_root()) / m.dataset_id / m.dataset_version
    if base.exists():
        raise FileExistsError(f"certified_package_immutable_refuse_overwrite:{base}")
    base.mkdir(parents=True)

    files: dict[str, str] = {
        "manifest.json": _dump(m.model_dump(mode="json")),
        "package.json": _dump(package.canonical_dict()),
        "provenance.json": _dump(_aggregate_provenance(package)),
        "certification.json": _dump(certification.as_dict()),
    }
    for name, text in files.items():
        (base / name).write_text(text, encoding="utf-8")

    checksums = {
        "content_hash": certification.content_hash,
        "files": {name: _sha256_text(text) for name, text in files.items()},
    }
    (base / "checksums.json").write_text(_dump(checksums), encoding="utf-8")
    return base


def verify_immutable(package_dir: Path) -> bool:
    """Recompute file checksums and confirm nothing was tampered with."""
    checksums_path = package_dir / "checksums.json"
    if not checksums_path.exists():
        return False
    stored = json.loads(checksums_path.read_text(encoding="utf-8"))
    for name, expected in stored.get("files", {}).items():
        fp = package_dir / name
        if not fp.exists():
            return False
        if _sha256_text(fp.read_text(encoding="utf-8")) != expected:
            return False
    return True

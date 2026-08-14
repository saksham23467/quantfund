#!/usr/bin/env python3
"""Produce a human-readable research dataset certification report.

Usage:
  .venv/bin/python scripts/certify_dataset.py --dataset-root path/to/dataset/version
  .venv/bin/python scripts/certify_dataset.py --dataset-id X --dataset-version Y
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quantfund.config import PATHS
from quantfund.data.certification import (
    certify,
    facts_from_manifest_and_quality,
    format_certification_report,
    write_certification,
)
from quantfund.data.datasets.manifest import DatasetManifest
from quantfund.data.quality.report import QualityReport


def _load_dataset(root: Path) -> tuple[DatasetManifest, QualityReport]:
    manifest = DatasetManifest.model_validate(
        json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    )
    qpath = root / "quality_report.json"
    if not qpath.exists() and manifest.quality_report_path:
        qpath = Path(manifest.quality_report_path)
    quality = QualityReport.model_validate(json.loads(qpath.read_text(encoding="utf-8")))
    return manifest, quality


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Certify a research dataset")
    parser.add_argument("--dataset-root", type=Path, default=None)
    parser.add_argument("--dataset-id", type=str, default=None)
    parser.add_argument("--dataset-version", type=str, default=None)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write certification.txt next to the dataset",
    )
    args = parser.parse_args(argv)

    if args.dataset_root is not None:
        root = args.dataset_root
    elif args.dataset_id and args.dataset_version:
        root = PATHS.datasets_dir / args.dataset_id / args.dataset_version
    else:
        parser.error("Provide --dataset-root or both --dataset-id and --dataset-version")
        return 2

    if not (root / "manifest.json").exists():
        print(f"ERROR: manifest.json not found under {root}", file=sys.stderr)
        return 1

    manifest, quality = _load_dataset(root)
    ca_coverage = str(manifest.lineage.get("corporate_action_coverage", "none"))
    delisted = str(manifest.lineage.get("delisted_coverage", "unknown"))
    facts = facts_from_manifest_and_quality(
        manifest=manifest,
        quality=quality,
        corporate_action_coverage=ca_coverage,
        delisted_coverage=delisted,
    )
    decision = certify(facts)
    report = format_certification_report(facts, decision)
    print(report)

    if args.write:
        out = write_certification(root / "certification.txt", facts=facts, decision=decision)
        print(f"Wrote {out}")

    return 0 if decision.is_research_eligible else 3


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Human-readable research dataset certification (Phase 3.5).

Usage:
  .venv/bin/python scripts/certify_research_dataset.py --dataset-root path/to/version
  .venv/bin/python scripts/certify_research_dataset.py \\
      --dataset-id india_eq_pilot_phase35 --dataset-version v1_synthetic
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.config import PATHS
from quantfund.data.certification import certify, facts_from_manifest_and_quality
from quantfund.data.datasets.manifest import DatasetManifest
from quantfund.data.quality.report import QualityReport, Severity


def _load(root: Path) -> tuple[DatasetManifest, QualityReport, dict]:
    manifest = DatasetManifest.model_validate(
        json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    )
    qpath = root / "quality_report.json"
    quality = QualityReport.model_validate(json.loads(qpath.read_text(encoding="utf-8")))
    provenance = {}
    prov_path = root / "provenance.json"
    if prov_path.exists():
        provenance = json.loads(prov_path.read_text(encoding="utf-8"))
    elif (root / "lineage").exists():
        pass
    # Prefer lineage provenance fields from manifest
    provenance = {**provenance, **(manifest.lineage or {})}
    return manifest, quality, provenance


def format_research_certification(
    manifest: DatasetManifest,
    quality: QualityReport,
    decision,
    facts,
) -> str:
    unverified_ca = [
        i
        for i in quality.issues
        if i.code in {"manual_corporate_action", "symbol_change_missing_instrument_id"}
    ]
    expected_absences = quality.expected_absences
    lines = [
        "RESEARCH DATASET CERTIFICATION",
        "================================",
        "",
        "DATASET",
        f"  id:              {manifest.dataset_id}",
        f"  version:         {manifest.dataset_version}",
        f"  content_hash:    {manifest.content_hash}",
        f"  bar_count:       {manifest.bar_count}",
        f"  instrument_count:{manifest.instrument_count}",
        "",
        "SOURCE",
        f"  source:          {manifest.source}",
        f"  source_grade:    {manifest.source_grade.value}",
        f"  download_id:     {manifest.download_id}",
        f"  date_range:      {manifest.date_range_start} .. {manifest.date_range_end}",
        "",
        "CALENDAR",
        f"  calendar_id:     {manifest.calendar_id}",
        f"  calendar_version:{manifest.calendar_version}",
        f"  calendar_verified:{manifest.calendar_verified}",
        "",
        "UNIVERSE",
        f"  universe_id:     {manifest.universe_id}",
        f"  universe_version:{manifest.universe_version}",
        f"  completeness:    {manifest.universe_completeness.value}",
        "",
        "CORPORATE ACTIONS",
        f"  coverage:        {manifest.lineage.get('corporate_action_coverage', 'unknown')}",
        f"  action_count:    {quality.corporate_action_count}",
        f"  unverified/manual flags: {len(unverified_ca)}",
        "",
        "DELISTED COVERAGE",
        f"  delisted_coverage: {manifest.lineage.get('delisted_coverage', 'unknown')}",
        "",
        "QUALITY",
        f"  errors:          {quality.error_count}",
        f"  warnings:        {quality.warning_count}",
        f"  expected_absences:{expected_absences}",
        f"  missing_sessions:{quality.missing_sessions}",
        f"  missing_bars:    {quality.missing_bars}",
        f"  duplicate_bars:  {quality.duplicate_bars}",
        f"  unknown_membership_sessions: {quality.unknown_membership_periods}",
        "",
        "ELIGIBILITY",
        f"  {decision.level.value.upper()}",
        "",
        "REASONS",
    ]
    for r in decision.reasons:
        lines.append(f"  - {r}")
    if decision.blockers:
        lines.append("")
        lines.append("BLOCKERS")
        for b in decision.blockers:
            lines.append(f"  - {b}")
    if decision.notes:
        lines.append("")
        lines.append("NOTES")
        for n in decision.notes:
            lines.append(f"  - {n}")

    # List ERROR codes explicitly
    errors = [i for i in quality.issues if i.severity == Severity.ERROR]
    if errors:
        lines.append("")
        lines.append("ERROR DETAIL")
        for i in errors[:20]:
            lines.append(f"  - [{i.code}] {i.message}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Certify a research dataset")
    parser.add_argument("--dataset-root", type=Path, default=None)
    parser.add_argument("--dataset-id", type=str, default=None)
    parser.add_argument("--dataset-version", type=str, default=None)
    parser.add_argument("--write", action="store_true")
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

    manifest, quality, _ = _load(root)
    facts = facts_from_manifest_and_quality(
        manifest=manifest,
        quality=quality,
        corporate_action_coverage=str(
            manifest.lineage.get("corporate_action_coverage", "none")
        ),
        delisted_coverage=str(manifest.lineage.get("delisted_coverage", "unknown")),
    )
    decision = certify(facts)
    report = format_research_certification(manifest, quality, decision, facts)
    print(report)

    if args.write:
        out = root / "CERTIFICATION_RESEARCH.txt"
        out.write_text(report, encoding="utf-8")
        print(f"Wrote {out}")

    return 0 if decision.is_research_eligible else 3


if __name__ == "__main__":
    raise SystemExit(main())

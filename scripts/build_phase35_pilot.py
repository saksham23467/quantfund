#!/usr/bin/env python3
"""Phase 3.5 pilot: RAW → dataset → certification for a small verified pipeline.

Uses the redistributable synthetic local research package by default so CI does
not redistribute proprietary market data. Result is expected DEVELOPMENT_ONLY
(source_grade=synthetic + partial NIFTY membership).

Never weakens ResearchEligibilityChecker.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.config import PATHS
from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.certification import (
    certify,
    facts_from_manifest_and_quality,
    format_certification_report,
)
from quantfund.data.datasets.builder import DatasetBuilder
from quantfund.data.datasets.manifest import SourceGrade
from quantfund.data.ingest.pipeline import ingest_bars_raw, load_raw_bars
from quantfund.data.instruments.master import InstrumentMasterStore
from quantfund.data.providers.local_package import LocalResearchPackageProvider
from quantfund.data.universe.import_membership import build_universe_from_membership_file
from quantfund.data.universe.models import UniverseCompleteness, VerificationStatus


def main() -> int:
    package_root = ROOT / "tests/fixtures/phase35/pilot_package"
    provider = LocalResearchPackageProvider(package_root)
    caps = provider.capabilities()
    print("Provider:", provider.name)
    print(" source_grade:", caps.source_grade.value)
    print(" exchange_authority:", caps.exchange_authority)
    print(" can_claim_research_eligible:", provider.can_claim_research_eligible)

    instruments = provider.get_instrument_master()
    # Persist instrument master version (immutable)
    master_store = InstrumentMasterStore(PATHS.data_dir / "instruments")
    master_version = "pilot_synthetic_v1"
    master_path = master_store.path_for("india_eq", master_version)
    if not master_path.exists():
        master_store.save(
            master_id="india_eq",
            master_version=master_version,
            instruments=instruments,
            source="phase35_synthetic_pilot",
            notes="Pilot instrument master from synthetic package (real ISINs, synthetic prices).",
        )

    download_id = "phase35_pilot_synthetic_v1"
    raw_path = PATHS.raw_dir / provider.name / download_id
    if raw_path.exists():
        print(f"Reusing immutable RAW download: {raw_path}")
        bars = load_raw_bars(raw_path)
        raw_root = raw_path
    else:
        result = ingest_bars_raw(
            provider=provider,
            instruments=instruments,
            raw_root=PATHS.raw_dir,
            start=datetime(2024, 1, 2),
            end=datetime(2024, 6, 28),
            download_id=download_id,
            extra_meta={
                "license_ref": "DATA_LICENSE.md#synthetic-fixtures",
                "package_id": provider.provenance().package_id,
                "package_version": provider.provenance().package_version,
                "phase": "3.5",
            },
        )
        print(f"RAW download_id={result.download_id} bars={result.bar_count}")
        print(f" provenance written: {result.root / 'provenance.json'}")
        bars = load_raw_bars(result.root)
        raw_root = result.root

    universe = build_universe_from_membership_file(
        ROOT
        / "data/universes/nifty50/universe_version=pit_partial_documented_v1/membership.csv",
        universe_id="nifty50",
        universe_version="pit_partial_documented_v1",
        effective_start=date(2023, 1, 1),
        effective_end=date(2025, 12, 31),
        source="NSE Indices Ltd reconstitution press releases (partial event log)",
        completeness=UniverseCompleteness.PARTIAL_PIT,
        verification_status=VerificationStatus.PARTIAL,
    )

    calendar = NSECalendarProvider()
    actions = provider.get_corporate_actions()

    dataset_id = "india_eq_pilot_phase35"
    dataset_version = "v1_synthetic"
    out = PATHS.datasets_dir / dataset_id / dataset_version
    builder = DatasetBuilder(PATHS.datasets_dir)
    if out.exists():
        print(f"Dataset already exists (immutable): {out}")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        quality = json.loads((out / "quality_report.json").read_text(encoding="utf-8"))
        from quantfund.data.datasets.manifest import DatasetManifest
        from quantfund.data.quality.report import QualityReport

        m = DatasetManifest.model_validate(manifest)
        q = QualityReport.model_validate(quality)
    else:
        m, q = builder.build(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            bars=bars,
            universe=universe,
            calendar=calendar,
            actions=actions,
            source=provider.name,
            download_id=download_id,
            raw_root=raw_root,
            source_grade=SourceGrade.SYNTHETIC,
            instruments=instruments,
            delisted_coverage="none",
            fail_on_quality_errors=True,
        )

    facts = facts_from_manifest_and_quality(
        manifest=m,
        quality=q,
        corporate_action_coverage=str(
            m.lineage.get("corporate_action_coverage", "none")
        ),
        delisted_coverage=str(m.lineage.get("delisted_coverage", "none")),
    )
    decision = certify(facts)
    report = format_certification_report(facts, decision)
    print()
    print(report)
    cert_path = PATHS.datasets_dir / dataset_id / dataset_version / "CERTIFICATION_RESEARCH.txt"
    cert_path.write_text(report, encoding="utf-8")
    print(f"Wrote {cert_path}")
    print("Eligibility:", decision.level.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

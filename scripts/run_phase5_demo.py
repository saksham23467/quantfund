#!/usr/bin/env python3
"""Phase 5 demo — research package validation + certification evidence.

DEVELOPMENT_ONLY unless QUANTFUND_RESEARCH_PACKAGE points to a genuinely
licensed research-grade package that passes all gates.

No brokers. No LLM. No strategy search. No fake exchange-grade data.
"""

from __future__ import annotations

import json
import os
import sys
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
from quantfund.data.corporate_actions.coverage import derive_ca_coverage_report
from quantfund.data.instruments.delisted import compute_delisted_coverage
from quantfund.data.providers.local_package import LocalResearchPackageProvider
from quantfund.data.providers.package_validator import validate_research_package
from quantfund.data.universe.coverage import compute_membership_coverage
from quantfund.data.universe.models import UniverseCompleteness, VerificationStatus


def _default_package() -> Path:
    env = os.environ.get("QUANTFUND_RESEARCH_PACKAGE")
    if env:
        return Path(env)
    return ROOT / "tests/fixtures/phase35/pilot_package"


def main() -> int:
    package_root = _default_package()
    print("PHASE 5 — Research data evidence demo")
    print("=" * 50)
    print(f"Package: {package_root}")
    if not os.environ.get("QUANTFUND_RESEARCH_PACKAGE"):
        print("Mode: DEVELOPMENT_ONLY synthetic fixture (default)")
        print("Set QUANTFUND_RESEARCH_PACKAGE for an external licensed package.")
    print()

    validation = validate_research_package(package_root)
    print("Package validation:", "PASS" if validation.valid else "FAIL")
    for e in validation.errors:
        print(f"  ERROR {e.code}: {e.message}")
    for w in validation.warnings:
        print(f"  WARNING {w.code}: {w.message}")
    if not validation.valid:
        return 2

    provider = LocalResearchPackageProvider(package_root, validate=False)
    caps = provider.capabilities()
    prov = provider.provenance()
    print()
    print("Provider / capabilities")
    print(f"  provider_id: {caps.provider_id}")
    print(f"  source_grade: {caps.source_grade.value}")
    print(f"  license_status: {caps.license_status.value}")
    print(f"  exchange_authority: {caps.exchange_authority}")
    print(f"  source_bar_ok: {caps.can_satisfy_research_eligibility_source_bar()}")
    print(f"  attestation_hash: {caps.attestation_hash()}")
    print(f"  package_content_hash: {validation.content_hash}")
    print(f"  provenance provider: {prov.provider} @ {prov.download_timestamp}")

    calendar = NSECalendarProvider()
    instruments = provider.get_instruments()
    actions = provider.get_corporate_actions()
    terminal = provider.get_terminal_events()
    symbols = [i.symbol for i in instruments]
    bars = []
    for sym in symbols:
        bars.extend(provider.get_history(sym))

    start = min(b.timestamp.date() for b in bars)
    end = max(b.timestamp.date() for b in bars)

    membership_path = (
        PATHS.data_dir
        / "universes"
        / "nifty50"
        / "universe_version=pit_partial_documented_v1"
        / "membership.json"
    )
    if membership_path.exists():
        from quantfund.data.universe.membership import UniverseMembershipStore

        universe = UniverseMembershipStore(PATHS.data_dir / "universes").load(
            "nifty50", "pit_partial_documented_v1"
        )
    else:
        # Fallback: minimal partial PIT from package symbols (still not research-grade)
        from quantfund.data.universe.membership import build_pit_universe
        from quantfund.data.universe.models import UniverseMembership

        universe = build_pit_universe(
            universe_id="nifty50",
            universe_version="phase5_demo_partial",
            memberships=[
                UniverseMembership(
                    universe_id="nifty50",
                    instrument_id=i.instrument_id or i.symbol,
                    symbol=i.symbol,
                    member_from=start,
                    member_to=None,
                    source="phase5_demo_synthetic",
                    verification_status=VerificationStatus.UNVERIFIED,
                )
                for i in instruments
            ],
            as_of_date=end,
            effective_start=start,
            effective_end=end,
            source="phase5_demo",
            completeness=UniverseCompleteness.PARTIAL_PIT,
        )

    mem_cov = compute_membership_coverage(
        universe,
        calendar=calendar,
        start=start,
        end=end,
        symbols=symbols,
    )
    ca_report = derive_ca_coverage_report(
        actions, source_grade=caps.source_grade.value
    )
    delisted = compute_delisted_coverage(
        instruments=instruments, events=terminal
    )

    print()
    print("Calendar")
    print(f"  {calendar.calendar_id} / {calendar.calendar_version} verified={calendar.verified}")
    print()
    print("Universe / membership coverage")
    print(f"  universe: {universe.universe_id} / {universe.universe_version}")
    print(f"  completeness: {universe.completeness.value}")
    print(f"  known_sessions: {mem_cov.known_membership_sessions}")
    print(f"  unknown_sessions: {mem_cov.unknown_membership_sessions}")
    print(f"  coverage_ratio: {mem_cov.membership_coverage_ratio:.4f}")
    print()
    print("Corporate-action coverage")
    for k, v in ca_report.to_dict().items():
        if k != "notes":
            print(f"  {k}: {v}")
    print()
    print(f"Delisted coverage: {delisted}")
    print(f"Terminal events: {len(terminal)}")
    print(f"Bars loaded: {len(bars)} instruments={len(symbols)}")

    # Prefer existing certified pilot dataset if present
    dataset_id = "india_eq_pilot_phase35"
    dataset_version = "v1_synthetic"
    ds = PATHS.datasets_dir / dataset_id / dataset_version
    if ds.exists() and (ds / "manifest.json").exists():
        from quantfund.data.datasets.manifest import DatasetManifest
        from quantfund.data.quality.report import QualityReport

        manifest = DatasetManifest.model_validate(
            json.loads((ds / "manifest.json").read_text(encoding="utf-8"))
        )
        quality = QualityReport.model_validate(
            json.loads((ds / "quality_report.json").read_text(encoding="utf-8"))
        )
        facts = facts_from_manifest_and_quality(
            manifest=manifest,
            quality=quality,
            corporate_action_coverage=str(
                manifest.lineage.get("corporate_action_coverage", ca_report.overall)
            ),
            delisted_coverage=str(
                manifest.lineage.get("delisted_coverage", delisted)
            ),
            membership_coverage_ratio=mem_cov.membership_coverage_ratio,
            capability_source_bar_ok=caps.can_satisfy_research_eligibility_source_bar(),
            provenance_complete=bool(prov.content_hashes or prov.request_parameters),
            license_status=caps.license_status.value,
            capability_attestation_hash=caps.attestation_hash(),
            package_content_hash=validation.content_hash,
            ca_coverage_breakdown=ca_report.to_dict(),
        )
    else:
        print()
        print(
            "Note: pilot dataset not built yet "
            f"({dataset_id}/{dataset_version}). "
            "Run make phase35-pilot first for full dataset certification path."
        )
        # Synthesize facts from package evidence alone
        from quantfund.data.policy import DatasetCertificationFacts
        from quantfund.data.quality.checks import run_quality_checks

        quality = run_quality_checks(
            bars,
            calendar=calendar,
            universe=universe,
            actions=actions,
            instruments=instruments,
            terminal_events=terminal,
            provider_capabilities=caps,
            dataset_id="phase5_demo_package",
            source=caps.provider_id,
            start=start,
            end=end,
        )
        facts = DatasetCertificationFacts(
            dataset_id="phase5_demo_package",
            dataset_version="ephemeral",
            source=str(prov.source),
            source_grade=caps.source_grade.value,
            calendar_id=calendar.calendar_id,
            calendar_version=calendar.calendar_version,
            calendar_verified=calendar.verified,
            universe_id=universe.universe_id,
            universe_version=universe.universe_version,
            universe_completeness=universe.completeness.value,
            corporate_action_coverage=ca_report.overall,
            adjustment_policy_id="split_bonus_v1",
            date_coverage_start=start.isoformat(),
            date_coverage_end=end.isoformat(),
            instrument_count=len(instruments),
            delisted_coverage=delisted,
            missing_sessions=quality.missing_sessions,
            missing_bars=quality.missing_bars,
            duplicate_bars=quality.duplicate_bars,
            invalid_ohlc=quality.invalid_ohlc,
            error_count=quality.error_count,
            warning_count=quality.warning_count,
            content_hash=validation.content_hash or "sha256:unknown",
            quality_error_codes=quality.error_codes(),
            unknown_membership_session_count=mem_cov.unknown_membership_sessions,
            instrument_identity_issues=quality.instrument_identity_problems,
            membership_coverage_ratio=mem_cov.membership_coverage_ratio,
            capability_source_bar_ok=caps.can_satisfy_research_eligibility_source_bar(),
            provenance_complete=bool(prov.download_timestamp),
            license_status=caps.license_status.value,
            capability_attestation_hash=caps.attestation_hash(),
            package_content_hash=validation.content_hash,
            ca_coverage_breakdown=ca_report.to_dict(),
        )

    decision = certify(facts)
    print()
    print(format_certification_report(facts, decision))
    print("Phase 4 contract: development_only ⇒ accepted strategies = 0")
    print("Phase 5 complete — no brokers / LLM / strategy search added.")
    return 0 if decision.level.value == "development_only" or decision.is_research_eligible else 0


if __name__ == "__main__":
    raise SystemExit(main())

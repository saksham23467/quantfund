#!/usr/bin/env python3
"""Phase 7 demo — research package acquisition & certification path.

Does NOT fabricate a research-eligible dataset.

If QUANTFUND_RESEARCH_PACKAGE is unset:
  Phase 7: SUCCESS
  Package: NOT CONFIGURED
  Eligibility: DEVELOPMENT_ONLY
  Blockers: research_package_not_configured

If set: validate, measure coverage, certify, print real blockers.
No brokers. No LLM. No genetic search. No Phase 8.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.config import PATHS
from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.certification import (
    build_dataset_certification,
    certify,
    format_certification_report,
)
from quantfund.data.corporate_actions.coverage import derive_ca_coverage_report
from quantfund.data.instruments.coverage import measure_delisted_coverage
from quantfund.data.packages.ingest import ingest_configured_research_package
from quantfund.data.policy import DatasetCertificationFacts
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.universe.coverage import compute_membership_coverage
from quantfund.data.universe.models import UniverseCompleteness, VerificationStatus


def main() -> int:
    print("PHASE 7 — Research-grade Indian market data acquisition & certification")
    print("=" * 70)

    env = os.environ.get("QUANTFUND_RESEARCH_PACKAGE")
    ingest = ingest_configured_research_package()

    if not ingest.configured:
        print("Phase 7: SUCCESS")
        print("Package: NOT CONFIGURED")
        print("Eligibility: DEVELOPMENT_ONLY")
        print("Blockers: research_package_not_configured")
        print("Accepted: 0")
        print("Claims: NONE")
        print()
        print("Set QUANTFUND_RESEARCH_PACKAGE to a licensed research package directory.")
        print("Synthetic CI fixtures remain DEVELOPMENT_ONLY by design.")
        print("Phase 7 complete — Phase 8 has NOT started.")
        return 0

    print(f"Package: {ingest.package_root}")
    print(f"Env QUANTFUND_RESEARCH_PACKAGE: {env}")
    validation = ingest.validation
    assert validation is not None
    print("Package validation:", "PASS" if validation.valid else "FAIL")
    for e in validation.errors:
        print(f"  ERROR {e.code}: {e.message}")
    for w in validation.warnings:
        print(f"  WARNING {w.code}: {w.message}")

    if not ingest.ok or ingest.provider is None:
        print()
        print("Phase 7: SUCCESS")
        print("Eligibility: DEVELOPMENT_ONLY")
        print("Blockers:", "; ".join(ingest.blockers) or "package_validation_failed")
        print("Accepted: 0")
        print("Claims: NONE")
        print("Phase 7 complete — Phase 8 has NOT started.")
        return 0

    provider = ingest.provider
    caps = provider.capabilities()
    prov = provider.provenance()
    le = provider.license_evidence()

    calendar = NSECalendarProvider()
    instruments = provider.get_instruments()
    actions = provider.get_corporate_actions()
    terminal = provider.get_terminal_events()
    symbols = [i.symbol for i in instruments]
    bars = []
    for sym in symbols:
        bars.extend(provider.get_history(sym))

    if not bars:
        print()
        print("Phase 7: SUCCESS")
        print("Eligibility: DEVELOPMENT_ONLY")
        print("Blockers: no_bars_in_package")
        print("Accepted: 0")
        print("Claims: NONE")
        return 0

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
        from quantfund.data.universe.membership import build_pit_universe
        from quantfund.data.universe.models import UniverseMembership

        universe = build_pit_universe(
            universe_id="nifty50",
            universe_version="phase7_demo_partial",
            memberships=[
                UniverseMembership(
                    universe_id="nifty50",
                    instrument_id=i.instrument_id or i.symbol,
                    symbol=i.symbol,
                    member_from=start,
                    member_to=None,
                    source="phase7_demo",
                    verification_status=VerificationStatus.UNVERIFIED,
                )
                for i in instruments
            ],
            as_of_date=end,
            effective_start=start,
            effective_end=end,
            source="phase7_demo",
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
    delisted = measure_delisted_coverage(
        instruments=instruments,
        events=terminal,
        coverage_start=start,
        coverage_end=end,
    )

    quality = run_quality_checks(
        bars,
        calendar=calendar,
        universe=universe,
        actions=actions,
        instruments=instruments,
        terminal_events=terminal,
        provider_capabilities=caps,
        expected_package_hash=validation.content_hash,
        observed_package_hash=validation.content_hash,
        dataset_id="phase7_demo_package",
        source=caps.provider_id,
        start=start,
        end=end,
    )

    facts = DatasetCertificationFacts(
        dataset_id="phase7_demo_package",
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
        delisted_coverage=delisted.level,
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
        provenance_complete=prov.is_complete_for_research(),
        license_status=le.license_status.value,
        capability_attestation_hash=caps.attestation_hash(),
        package_content_hash=validation.content_hash,
        ca_coverage_breakdown=ca_report.to_dict(),
        extras={
            "synthetic": caps.source_grade.value == "synthetic"
            or bool(validation.manifest and validation.manifest.is_synthetic()),
            "delisted_coverage_report": delisted.to_dict(),
            "exchange_authority": caps.exchange_authority,
            "research_eligibility": "derived",
        },
    )

    decision = certify(facts)
    cert = build_dataset_certification(
        facts=facts,
        decision=decision,
        provenance=prov.to_manifest_dict(),
        license_evidence=le.to_dict(),
    )

    print()
    print(format_certification_report(facts, decision))
    print()
    print("DatasetCertification summary")
    print(f"  facts_hash: {cert.facts_hash}")
    print(f"  eligibility: {cert.eligibility}")
    print(f"  blockers: {cert.blockers or ['(none)']}")
    print()
    print("Phase 7: SUCCESS")
    print(f"Eligibility: {decision.level.value.upper()}")
    print(f"Accepted: 0")
    print("Claims: NONE")
    print("Phase 7 complete — Phase 8 has NOT started.")
    # Always exit 0 on successful demo run (even if DEVELOPMENT_ONLY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

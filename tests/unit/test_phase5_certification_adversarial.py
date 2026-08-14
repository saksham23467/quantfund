"""Phase 5 — certification forge-resistance and adversarial quality."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.certification import (
    certify,
    facts_hash,
    load_and_verify_certification,
    verify_facts_integrity,
    write_certification,
)
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.data.grades import SourceGrade
from quantfund.data.providers.capabilities import ProviderCapabilities
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.universe.membership import build_pit_universe
from quantfund.data.universe.models import (
    UniverseMembership,
    VerificationStatus,
)


def _good_research_facts(**overrides) -> DatasetCertificationFacts:
    base = dict(
        dataset_id="x",
        dataset_version="v1",
        source="licensed_vendor",
        source_grade="paid",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="nifty50",
        universe_version="full",
        universe_completeness="partial_pit",
        corporate_action_coverage="splits_bonus_dividends",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-06-28",
        instrument_count=10,
        delisted_coverage="partial",
        content_hash="sha256:abc",
        error_count=0,
        warning_count=0,
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        capability_source_bar_ok=True,
        provenance_complete=True,
        license_status="internal_research_only",
    )
    base.update(overrides)
    return DatasetCertificationFacts(**base)


def test_synthetic_facts_development_only():
    facts = _good_research_facts(source_grade="synthetic", capability_source_bar_ok=False)
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_incomplete_pit_unknowns_block_research():
    facts = _good_research_facts(unknown_membership_session_count=5, membership_coverage_ratio=0.9)
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("unknown_membership" in b for b in d.blockers)


def test_missing_delisted_blocks_research_and_production():
    facts = _good_research_facts(delisted_coverage="none")
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("delisted_coverage" in b for b in d.blockers)

    facts2 = _good_research_facts(
        delisted_coverage="partial", universe_completeness="full_pit",
        corporate_action_coverage="full_verified",
    )
    d2 = ResearchEligibilityChecker().evaluate(facts2)
    assert d2.level == EligibilityLevel.RESEARCH_ELIGIBLE
    assert any("delisted_coverage" in n for n in d2.notes)


def test_manifest_research_eligible_flag_ignored_in_extras():
    facts = _good_research_facts(
        source_grade="synthetic",
        capability_source_bar_ok=False,
        extras={"research_eligible": True},
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("Ignored" in n for n in d.notes)


def test_facts_hash_mismatch_detected(tmp_path: Path):
    facts = _good_research_facts()
    decision = certify(facts)
    path = write_certification(tmp_path / "certification.txt", facts=facts, decision=decision)
    sidecar = path.with_suffix(".json")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    data["facts"]["source_grade"] = "exchange"
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    loaded, ok = load_and_verify_certification(sidecar)
    assert ok is False
    assert loaded.source_grade == "exchange"


def test_certificate_recompute_deterministic():
    facts = _good_research_facts()
    h1 = facts_hash(facts)
    h2 = facts_hash(facts)
    assert h1 == h2
    assert verify_facts_integrity(facts, h1)


def test_full_pit_rejected_when_unknowns_remain():
    facts = _good_research_facts(
        universe_completeness="full_pit",
        unknown_membership_session_count=1,
        membership_coverage_ratio=0.99,
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("full_pit claim rejected" in b for b in d.blockers)


def test_metrics_still_cannot_promote_eligibility():
    facts = _good_research_facts(
        source_grade="non_exchange",
        capability_source_bar_ok=False,
        extras={"sharpe": 10.0},
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_yfinance_capabilities_fail_source_bar_in_quality():
    cal = FakeCalendarProvider([date(2024, 1, 2)], verified=True)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="A",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
    ]
    forged = ProviderCapabilities(
        provider_id="yfinance",
        provider_name="Yahoo",
        source_grade=SourceGrade.NON_EXCHANGE,
        exchange_authority=True,
    )
    report = run_quality_checks(bars, calendar=cal, provider_capabilities=forged)
    assert any(i.code == "capability_forgery" for i in report.issues)


def test_post_delisting_bars_error():
    cal = FakeCalendarProvider([date(2024, 1, 2), date(2024, 1, 3)], verified=True)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="G",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 3),
            symbol="G",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
    ]
    inst = Instrument(
        symbol="G",
        exchange="NSE",
        isin="INE111A01001",
        delisting_date=date(2024, 1, 2),
    )
    report = run_quality_checks(bars, calendar=cal, instruments=[inst])
    assert any(i.code == "post_delisting_bar" for i in report.issues)


def test_bar_on_closed_session_error():
    cal = FakeCalendarProvider([date(2024, 1, 2)], verified=True)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 3),  # not an open session
            symbol="A",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
    ]
    report = run_quality_checks(bars, calendar=cal)
    assert any(i.code == "bar_on_closed_session" for i in report.issues)


def test_future_membership_leak_with_explicit_asof():
    cal = FakeCalendarProvider([date(2024, 1, 2)], verified=True)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="A",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
    ]
    u = build_pit_universe(
        universe_id="u",
        universe_version="t",
        memberships=[
            UniverseMembership(
                universe_id="u",
                instrument_id="NSE:B",
                symbol="B",
                member_from=date(2024, 6, 1),
                member_to=None,
                source="t",
                verification_status=VerificationStatus.VERIFIED,
            )
        ],
        as_of_date=date(2024, 6, 1),
        effective_start=date(2024, 1, 1),
        effective_end=date(2024, 12, 31),
        source="t",
    )
    report = run_quality_checks(
        bars, calendar=cal, universe=u, asof_date=date(2024, 1, 2)
    )
    assert any(i.code == "future_membership_visible" for i in report.issues)


def test_package_checksum_mismatch_error():
    cal = FakeCalendarProvider([date(2024, 1, 2)], verified=True)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="A",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
    ]
    report = run_quality_checks(
        bars,
        calendar=cal,
        expected_package_hash="sha256:aaa",
        observed_package_hash="sha256:bbb",
    )
    assert any(i.code == "package_checksum_mismatch" for i in report.issues)


def test_wrong_calendar_still_surfaces_missing_session():
    nse = NSECalendarProvider()
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 24),
            symbol="A",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 29),
            symbol="A",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
    ]
    report = run_quality_checks(
        bars, calendar=nse, start=date(2024, 1, 24), end=date(2024, 1, 29)
    )
    assert any(i.code == "missing_open_session" for i in report.issues)


def test_research_eligible_path_requires_all_phase5_gates():
    d = ResearchEligibilityChecker().evaluate(_good_research_facts())
    assert d.level == EligibilityLevel.RESEARCH_ELIGIBLE


def test_capability_source_bar_required():
    facts = _good_research_facts(capability_source_bar_ok=False)
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("capability_source_bar" in b for b in d.blockers)


def test_unknown_license_blocks_research():
    facts = _good_research_facts(license_status="unknown")
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_phase4_pipeline_still_rejects_development_only():
    """Smoke: development_only eligibility still forces accepted=False semantics."""
    from quantfund.data.policy import EligibilityLevel as EL

    facts = _good_research_facts(source_grade="synthetic", capability_source_bar_ok=False)
    decision = ResearchEligibilityChecker().evaluate(facts)
    assert decision.level == EL.DEVELOPMENT_ONLY
    assert decision.is_research_eligible is False

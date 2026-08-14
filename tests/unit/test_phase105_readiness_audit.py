"""Phase 10.5 — research package readiness audit (no gate weakening)."""

from __future__ import annotations

from pathlib import Path

from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.packages.readiness import (
    AUDIT_CATEGORIES,
    audit_research_package,
    format_readiness_report,
)
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "phase35"
    / "pilot_package"
)


def test_audit_demo_fixture_not_research_eligible():
    report = audit_research_package(FIXTURE)
    assert report.research_eligible is False
    assert report.eligibility_level == "development_only"
    assert report.paper_data_rung_ready is False
    assert report.to_dict()["eligibility_gates_weakened"] is False
    assert report.to_dict()["phase11_started"] is True
    assert report.to_dict()["phase12_started"] is True
    assert report.to_dict()["phase13_started"] is True
    assert report.to_dict()["phase14_started"] is True
    assert report.to_dict()["phase15_started"] is True
    assert report.to_dict()["phase16a_started"] is True
    assert report.to_dict()["phase16b_started"] is True


def test_audit_reports_blocking_source_grade_and_delisted():
    report = audit_research_package(FIXTURE)
    blob = " ".join(report.blockers).lower()
    assert "synthetic" in blob or "source_grade" in blob
    assert "delisted" in blob


def test_audit_category_table_complete():
    report = audit_research_package(FIXTURE)
    names = {c.name for c in report.categories}
    for required in [
        "Market data",
        "Instrument identity",
        "NIFTY50 PIT",
        "UNKNOWN membership",
        "Corporate actions",
        "Delisted coverage",
        "NSE calendar",
        "Provenance",
        "License",
        "Checksums",
        "Quality",
        "Source grade / capability bar",
    ]:
        assert required in names


def test_format_contains_research_eligible_false():
    text = format_readiness_report(audit_research_package(FIXTURE))
    assert "RESEARCH_ELIGIBLE: FALSE" in text
    assert "Market data" in text
    assert "Blockers:" in text


def test_unconfigured_without_fixture_not_configured():
    report = audit_research_package(None, default_demo_fixture=None)
    assert report.configured is False
    assert report.research_eligible is False
    assert "research_package_not_configured" in report.blockers


def test_default_fixture_path_when_unset():
    report = audit_research_package(None, default_demo_fixture=FIXTURE)
    assert report.package_root is not None
    assert report.configured is False  # env not set; auditing fixture
    assert report.research_eligible is False


def test_requirement_catalog_has_blocking_items():
    report = audit_research_package(FIXTURE)
    assert len(report.requirements) >= 10
    blocking = [r for r in report.requirements if r.blocking_severity == "BLOCKING"]
    assert blocking
    assert any(r.category == "Delisted coverage" for r in report.requirements)


def test_mergers_not_required_note_present():
    report = audit_research_package(FIXTURE)
    assert any("merger" in n.lower() for n in report.notes)
    ca = next(r for r in report.requirements if r.category == "Corporate actions")
    assert "merger" in (ca.detail or "").lower()


def test_eligibility_checker_unchanged_on_synthetic_facts():
    """Guard: readiness must not alter ResearchEligibilityChecker behavior."""
    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="v1",
        source="synthetic",
        source_grade="synthetic",
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
        instrument_count=8,
        delisted_coverage="partial",
        content_hash="sha256:abc",
        error_count=0,
        warning_count=0,
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        capability_source_bar_ok=False,
        provenance_complete=True,
        license_status="redistributable",
        extras={"synthetic": True},
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_audit_categories_constant_stable():
    assert "Market data" in AUDIT_CATEGORIES
    assert "License" in AUDIT_CATEGORIES


def test_package_valid_true_but_not_research_eligible():
    report = audit_research_package(FIXTURE)
    # Pilot validates structurally but fails research eligibility
    assert report.package_valid is True
    assert report.research_eligible is False

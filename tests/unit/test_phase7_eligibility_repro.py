"""Phase 7 — eligibility gates + reproducibility + integration."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from quantfund.data.certification import (
    build_dataset_certification,
    certify,
    facts_hash,
)
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.grades import SourceGrade
from quantfund.data.packages.ingest import ingest_configured_research_package
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.data.providers.capabilities import (
    yfinance_capabilities,
    synthetic_capabilities,
)
from quantfund.data.providers.local_package import LocalResearchPackageProvider
from quantfund.data.providers.package_validator import validate_research_package

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "phase35" / "pilot_package"


def _base_facts(**overrides) -> DatasetCertificationFacts:
    data = dict(
        dataset_id="t",
        dataset_version="v1",
        source="vendor",
        source_grade="exchange",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="nifty50",
        universe_version="pit_full",
        universe_completeness="full_pit",
        corporate_action_coverage="splits_bonus_dividends",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-06-28",
        instrument_count=50,
        delisted_coverage="partial",
        missing_sessions=0,
        missing_bars=0,
        duplicate_bars=0,
        invalid_ohlc=0,
        error_count=0,
        warning_count=0,
        content_hash="sha256:abc",
        quality_error_codes=[],
        unknown_membership_session_count=0,
        instrument_identity_issues=0,
        membership_coverage_ratio=1.0,
        capability_source_bar_ok=True,
        provenance_complete=True,
        license_status="verified",
        capability_attestation_hash="sha256:cap",
        package_content_hash="sha256:pkg",
        ca_coverage_breakdown={},
        extras={"synthetic": False},
    )
    data.update(overrides)
    return DatasetCertificationFacts(**data)


def test_synthetic_always_rejected():
    d = ResearchEligibilityChecker().evaluate(
        _base_facts(source_grade="synthetic", capability_source_bar_ok=False)
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("synthetic" in b or "source_grade" in b for b in d.blockers)


def test_synthetic_flag_extras_rejected():
    d = ResearchEligibilityChecker().evaluate(
        _base_facts(extras={"synthetic": True})
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("synthetic=true" in b for b in d.blockers)


def test_yfinance_capabilities_never_source_bar():
    assert yfinance_capabilities().can_satisfy_research_eligibility_source_bar() is False


def test_yfinance_facts_rejected():
    d = ResearchEligibilityChecker().evaluate(
        _base_facts(
            source="yfinance",
            source_grade="non_exchange",
            capability_source_bar_ok=False,
            license_status="unknown",
        )
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_unknown_membership_rejected():
    d = ResearchEligibilityChecker().evaluate(
        _base_facts(unknown_membership_session_count=3, membership_coverage_ratio=0.9)
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("unknown_membership" in b for b in d.blockers)


def test_missing_delisted_coverage_rejected():
    d = ResearchEligibilityChecker().evaluate(
        _base_facts(delisted_coverage="none")
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("delisted_coverage" in b for b in d.blockers)


def test_bad_license_unknown_rejected():
    d = ResearchEligibilityChecker().evaluate(_base_facts(license_status="unknown"))
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("license_status=unknown" in b for b in d.blockers)


def test_bad_license_expired_rejected():
    d = ResearchEligibilityChecker().evaluate(_base_facts(license_status="expired"))
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("expired" in b for b in d.blockers)


def test_bad_provenance_rejected():
    d = ResearchEligibilityChecker().evaluate(_base_facts(provenance_complete=False))
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("provenance" in b for b in d.blockers)


def test_unverified_calendar_rejected():
    d = ResearchEligibilityChecker().evaluate(_base_facts(calendar_verified=False))
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("calendar_verified" in b for b in d.blockers)


def test_quality_error_rejected():
    d = ResearchEligibilityChecker().evaluate(
        _base_facts(error_count=2, quality_error_codes=["invalid_ohlc"])
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("quality ERROR" in b for b in d.blockers)


def test_identical_facts_same_hash():
    a = _base_facts()
    b = _base_facts()
    assert facts_hash(a) == facts_hash(b)


def test_changed_source_changes_hash():
    a = _base_facts(source="vendor_a")
    b = _base_facts(source="vendor_b")
    assert facts_hash(a) != facts_hash(b)


def test_changed_membership_ratio_changes_hash():
    a = _base_facts(membership_coverage_ratio=1.0)
    b = _base_facts(membership_coverage_ratio=0.95)
    assert facts_hash(a) != facts_hash(b)


def test_changed_ca_coverage_changes_hash():
    a = _base_facts(corporate_action_coverage="none")
    b = _base_facts(corporate_action_coverage="splits_bonus_dividends")
    assert facts_hash(a) != facts_hash(b)


def test_certification_object_reproducible_facts_hash():
    facts = _base_facts(
        # Still development due to delisted partial vs production, but research possible
        delisted_coverage="partial",
    )
    decision = certify(facts)
    cert = build_dataset_certification(facts=facts, decision=decision)
    assert cert.facts_hash == facts_hash(facts)
    assert cert.eligibility == decision.level.value


def test_synthetic_package_development_only_integration():
    r = validate_research_package(FIXTURE)
    assert r.valid
    provider = LocalResearchPackageProvider(FIXTURE, validate=False)
    assert provider.source_grade == SourceGrade.SYNTHETIC
    assert provider.capabilities().can_satisfy_research_eligibility_source_bar() is False
    facts = _base_facts(
        source=provider.name,
        source_grade="synthetic",
        capability_source_bar_ok=False,
        license_status="redistributable",
        extras={"synthetic": True},
    )
    decision = certify(facts)
    assert decision.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_no_package_safe_failure(monkeypatch):
    monkeypatch.delenv("QUANTFUND_RESEARCH_PACKAGE", raising=False)
    result = ingest_configured_research_package()
    assert result.ok is False
    assert "research_package_not_configured" in result.blockers


def test_external_package_path_works(monkeypatch):
    monkeypatch.setenv("QUANTFUND_RESEARCH_PACKAGE", str(FIXTURE))
    result = ingest_configured_research_package()
    assert result.configured is True
    assert result.ok is True
    assert result.validation is not None
    assert result.validation.content_hash


def test_full_certification_report_generated():
    facts = _base_facts(source_grade="synthetic", capability_source_bar_ok=False)
    decision = certify(facts)
    cert = build_dataset_certification(
        facts=facts,
        decision=decision,
        provenance={"provider": "synthetic"},
        license_evidence={"license_status": "redistributable"},
    )
    payload = cert.to_dict()
    assert "facts_hash" in payload
    assert "quality_summary" in payload
    assert payload["eligibility"] == "development_only"


def test_package_hash_stable_for_identical_tree(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    shutil.copytree(FIXTURE, a)
    shutil.copytree(FIXTURE, b)
    ha = validate_research_package(a).content_hash
    hb = validate_research_package(b).content_hash
    assert ha == hb


def test_changed_membership_file_changes_package_hash(tmp_path: Path):
    dest = tmp_path / "pkg"
    shutil.copytree(FIXTURE, dest)
    h1 = validate_research_package(dest).content_hash
    # mutate a bar file
    bar = next((dest / "bars").glob("*.csv"))
    text = bar.read_text(encoding="utf-8")
    bar.write_text(text + "\n", encoding="utf-8")
    h2 = validate_research_package(dest).content_hash
    assert h1 != h2


def test_synthetic_capabilities_declare_limits():
    caps = synthetic_capabilities()
    assert caps.supports_daily_bars is True
    assert caps.exchange_authority is False
    assert caps.can_satisfy_research_eligibility_source_bar() is False

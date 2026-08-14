"""Phase 10 — acceptance records, certification gates, research data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.research.acceptance_record import (
    build_acceptance_record,
    load_acceptance_record,
    make_acceptance_evidence_id,
    verify_acceptance_record,
    write_acceptance_record,
)
from quantfund.research.certify_package import certify_research_package
from quantfund.research.promotion import run_phase10_pipeline_synthetic


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


def _accepted_record(**overrides):
    kwargs = dict(
        campaign_id="camp1",
        strategy_id="strat_a",
        strategy_version="1.0.0",
        dataset_id="ds",
        dataset_version="v1",
        config_hash="cfghash",
        selection_criterion="validation_sharpe",
        research_eligibility="research_eligible",
        sealed_test_ok=True,
        robustness_ok=True,
        walkforward_ok=True,
        dsr_trial_accounting_ok=True,
        no_leakage=True,
        no_unknown_membership_traded=True,
        dsr=0.5,
        n_trials=10,
        score=1.2,
        test_metrics={"sharpe": 1.1},
        validation_metrics={"sharpe": 1.0},
        walkforward_metrics={"fraction_positive_windows": 0.6},
        robustness_summary={"pass_rate": 0.8, "fragile": False},
    )
    kwargs.update(overrides)
    return build_acceptance_record(**kwargs)


def test_valid_licensed_facts_research_eligible():
    d = ResearchEligibilityChecker().evaluate(_good_research_facts())
    assert d.level == EligibilityLevel.RESEARCH_ELIGIBLE


def test_invalid_synthetic_package_facts_development_only():
    d = ResearchEligibilityChecker().evaluate(
        _good_research_facts(source_grade="synthetic", capability_source_bar_ok=False)
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_checksum_mismatch_blocks_via_quality_errors():
    facts = _good_research_facts(
        error_count=1, quality_error_codes=["content_hash_mismatch"]
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_provenance_incomplete_blocks():
    d = ResearchEligibilityChecker().evaluate(
        _good_research_facts(provenance_complete=False)
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_incomplete_pit_unknown_membership_blocks():
    d = ResearchEligibilityChecker().evaluate(
        _good_research_facts(unknown_membership_session_count=3)
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_delisted_none_blocks():
    d = ResearchEligibilityChecker().evaluate(
        _good_research_facts(delisted_coverage="none")
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_ca_none_blocks():
    d = ResearchEligibilityChecker().evaluate(
        _good_research_facts(corporate_action_coverage="none")
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_calendar_unverified_blocks():
    d = ResearchEligibilityChecker().evaluate(
        _good_research_facts(calendar_verified=False)
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_quality_errors_block():
    d = ResearchEligibilityChecker().evaluate(
        _good_research_facts(error_count=2, invalid_ohlc=2)
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_yfinance_non_exchange_development_only():
    d = ResearchEligibilityChecker().evaluate(
        _good_research_facts(
            source_grade="non_exchange",
            capability_source_bar_ok=False,
            source="yfinance",
        )
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_unconfigured_package_certify_development_only():
    elig, facts, blockers, meta = certify_research_package(None)
    assert elig == "development_only"
    assert facts is None
    assert "research_package_not_configured" in blockers
    assert meta["configured"] is False


def test_acceptance_record_deterministic_id():
    a = _accepted_record()
    b = _accepted_record()
    assert a.acceptance_evidence_id == b.acceptance_evidence_id
    assert a.artifact_digest == b.artifact_digest


def test_acceptance_id_changes_with_config():
    a = _accepted_record(config_hash="a")
    b = _accepted_record(config_hash="b")
    assert a.acceptance_evidence_id != b.acceptance_evidence_id


def test_acceptance_rejects_development_only():
    with pytest.raises(ValueError, match="development_only"):
        _accepted_record(research_eligibility="development_only")


def test_acceptance_requires_sealed_test():
    with pytest.raises(ValueError, match="sealed_test"):
        _accepted_record(sealed_test_ok=False)


def test_acceptance_requires_robustness():
    with pytest.raises(ValueError, match="robustness"):
        _accepted_record(robustness_ok=False)


def test_verify_detects_digest_tamper(tmp_path: Path):
    rec = _accepted_record()
    path = tmp_path / "a.json"
    write_acceptance_record(path, rec)
    raw = json.loads(path.read_text())
    raw["score"] = 999.0
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="invalid"):
        load_acceptance_record(path)


def test_verify_leakage_flag():
    rec = _accepted_record(no_leakage=False)
    assert "leakage_flagged" in verify_acceptance_record(rec)


def test_verify_unknown_membership():
    rec = _accepted_record(no_unknown_membership_traded=False)
    assert "unknown_membership_traded" in verify_acceptance_record(rec)


def test_make_acceptance_evidence_id_stable():
    i1 = make_acceptance_evidence_id(
        campaign_id="c",
        strategy_id="s",
        strategy_version="1",
        config_hash="h",
        dataset_id="d",
        dataset_version="v",
    )
    i2 = make_acceptance_evidence_id(
        campaign_id="c",
        strategy_id="s",
        strategy_version="1",
        config_hash="h",
        dataset_id="d",
        dataset_version="v",
    )
    assert i1 == i2


def test_synthetic_pipeline_mode_a():
    snap = run_phase10_pipeline_synthetic()
    assert snap.research_eligibility == "development_only"
    assert snap.paper_eligible is False
    assert snap.accepted_count == 0
    assert snap.real_orders == 0
    assert snap.claims == "NONE"
    assert snap.live_eligible is False
    assert snap.report["paper_session"] == "BLOCKED"


def test_acceptance_roundtrip(tmp_path: Path):
    rec = _accepted_record()
    path = write_acceptance_record(tmp_path / "ok.json", rec)
    loaded = load_acceptance_record(path)
    assert loaded.acceptance_evidence_id == rec.acceptance_evidence_id


def test_license_unknown_blocks():
    d = ResearchEligibilityChecker().evaluate(
        _good_research_facts(license_status="unknown")
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_current_snapshot_universe_blocks():
    d = ResearchEligibilityChecker().evaluate(
        _good_research_facts(universe_completeness="current_snapshot_only")
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY

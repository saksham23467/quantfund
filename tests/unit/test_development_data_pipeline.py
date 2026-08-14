"""DEVELOPMENT_DATA pipeline — engineering only; never research/paper/live eligible."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from quantfund.data.development.config import DATA_CLASS_DEVELOPMENT, DevelopmentIngestConfig
from quantfund.data.development.ingest import ingest_development_data
from quantfund.data.development.manifest import DevelopmentManifest, build_manifest
from quantfund.data.development.normalize import load_ohlcv_csv
from quantfund.data.development.provider import DevelopmentDataProvider
from quantfund.data.development.quality import run_development_quality_checks
from quantfund.data.development.report import format_development_report
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.models import MarketBar
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.execution.gateway import ExecutionMode
from quantfund.execution.live_eligibility import LiveTradingEligibilityGate
from quantfund.paper.eligibility import PaperEligibilityGate
from quantfund.paper.models import SessionMode
from quantfund.research.acceptance_record import build_acceptance_record


FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "development" / "sample_ohlcv"
)


def _dev_facts(**overrides) -> DatasetCertificationFacts:
    base = dict(
        dataset_id="india_eq_development",
        dataset_version="v1",
        source="development_free_nse",
        source_grade="development",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="dev",
        universe_version="current_snapshot",
        universe_completeness="full_pit",
        corporate_action_coverage="full_verified",
        adjustment_policy_id="none",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-06-01",
        instrument_count=50,
        delisted_coverage="complete",
        content_hash="sha256:abc",
        error_count=0,
        unknown_membership_session_count=0,
        membership_coverage_ratio=1.0,
        capability_source_bar_ok=True,
        provenance_complete=True,
        license_status="redistributable",
        data_class=DATA_CLASS_DEVELOPMENT,
        extras={"data_class": DATA_CLASS_DEVELOPMENT, "synthetic": False},
    )
    base.update(overrides)
    return DatasetCertificationFacts(**base)


def test_free_source_classified_development_data():
    p = DevelopmentDataProvider.from_file(FIXTURE)
    assert p.data_class == DATA_CLASS_DEVELOPMENT
    assert p.source_grade == "development"
    assert p.research_grade is False


def test_never_research_grade():
    assert DevelopmentDataProvider(bars=[]).research_grade is False
    assert DevelopmentDataProvider(bars=[]).exchange_authority is False


def test_synthetic_distinguishable_from_real_free():
    real = DevelopmentDataProvider(bars=[], synthetic=False)
    syn = DevelopmentDataProvider(bars=[], synthetic=True)
    assert real.synthetic is False
    assert syn.synthetic is True
    assert real.data_class == syn.data_class == DATA_CLASS_DEVELOPMENT


def test_manifest_created_and_hashed(tmp_path: Path):
    cfg = DevelopmentIngestConfig(
        file_path=FIXTURE,
        output_root=tmp_path / "dev",
        dataset_version="t1",
    )
    result = ingest_development_data(cfg)
    assert result.success
    assert result.manifest_path and result.manifest_path.exists()
    m = DevelopmentManifest.model_validate(
        json.loads(result.manifest_path.read_text())
    )
    assert m.content_hash.startswith("sha256:")
    assert m.content_hash != "sha256:pending"


def test_manifest_cannot_self_authorize():
    m = build_manifest(
        dataset_id="x",
        dataset_version="v",
        content_hash="sha256:x",
        synthetic=False,
        source="s",
        universe_mode="CURRENT_SNAPSHOT",
        corporate_action_coverage="none",
        delisted_coverage="none",
        instrument_count=1,
        bar_count=1,
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-01-02",
        quality_pass=True,
        quality_error_count=0,
        quality_warning_count=0,
    )
    # Even if caller tries True, validators force False
    assert m.research_eligible is False
    assert m.paper_eligible is False
    assert m.live_eligible is False
    assert m.research_grade is False


def test_manifest_data_class_immutable():
    with pytest.raises(Exception):
        DevelopmentManifest(
            dataset_id="x",
            dataset_version="v",
            data_class="RESEARCH_DATA",
            generated_at="t",
            content_hash="sha256:x",
            research_eligible=True,
        )


def test_valid_bars_accepted():
    bars = load_ohlcv_csv(FIXTURE / "bars" / "RELIANCE.csv", default_symbol="RELIANCE")
    assert len(bars) >= 2
    q = run_development_quality_checks(bars)
    assert q.ok is True


def test_duplicate_bars_detected():
    b = MarketBar(
        timestamp=datetime(2024, 1, 2),
        symbol="AAA",
        open=1,
        high=2,
        low=1,
        close=1.5,
        volume=10,
    )
    q = run_development_quality_checks([b, b])
    assert q.duplicate_bars >= 1
    assert q.ok is False


def test_invalid_ohlc_detected():
    b = MarketBar.model_construct(
        timestamp=datetime(2024, 1, 2),
        symbol="AAA",
        open=10.0,
        high=9.0,
        low=8.0,
        close=9.0,
        volume=1.0,
    )
    q = run_development_quality_checks([b])
    assert q.invalid_ohlc >= 1
    assert q.ok is False


def test_negative_volume_detected():
    # Construct via model_construct to bypass validators if any
    b = MarketBar.model_construct(
        timestamp=datetime(2024, 1, 2),
        symbol="AAA",
        open=1.0,
        high=2.0,
        low=1.0,
        close=1.5,
        volume=-5.0,
    )
    q = run_development_quality_checks([b])
    assert q.negative_volume >= 1


def test_empty_bars_fail_quality():
    q = run_development_quality_checks([])
    assert q.ok is False


def test_missing_pit_not_fabricated(tmp_path: Path):
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "d", dataset_version="pit1"
        )
    )
    m = json.loads(result.manifest_path.read_text())
    assert m["pit_membership"] == "unavailable"
    # Must not invent historical membership rows
    membership = result.root / "metadata" / "membership.json"
    assert not membership.exists() or json.loads(membership.read_text()) == []


def test_current_snapshot_not_pit(tmp_path: Path):
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "d", dataset_version="u1"
        )
    )
    m = DevelopmentManifest.model_validate(
        json.loads(result.manifest_path.read_text())
    )
    assert m.universe_mode == "CURRENT_SNAPSHOT"
    assert m.pit_membership == "unavailable"
    assert result.facts is not None
    assert result.facts.universe_completeness == "current_snapshot_only"


def test_missing_ca_explicit(tmp_path: Path):
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "d", dataset_version="ca1"
        )
    )
    m = json.loads(result.manifest_path.read_text())
    assert m["corporate_action_coverage"] == "none"


def test_delisted_none(tmp_path: Path):
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "d", dataset_version="dl1"
        )
    )
    assert json.loads(result.manifest_path.read_text())["delisted_coverage"] == "none"


def test_development_data_always_development_only():
    """Even with perfect research-looking facts, DEVELOPMENT_DATA stays locked."""
    d = ResearchEligibilityChecker().evaluate(_dev_facts())
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert d.is_research_eligible is False
    assert any("DEVELOPMENT_DATA" in b for b in d.blockers)


def test_development_source_grade_blocks():
    d = ResearchEligibilityChecker().evaluate(
        _dev_facts(data_class="", extras={}, source_grade="development")
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_never_research_eligible_via_quality():
    d = ResearchEligibilityChecker().evaluate(_dev_facts(error_count=0))
    assert "research_eligible" not in d.level.value or d.level.value == "development_only"


def test_paper_eligible_false(tmp_path: Path):
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "d", dataset_version="p1"
        )
    )
    assert result.paper_eligible is False
    paper = PaperEligibilityGate().evaluate(
        certified_eligibility="development_only",
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id="x",
        facts=result.facts,
        sealed_test_ok=True,
        robustness_ok=True,
        walkforward_ok=True,
        dsr_trial_accounting_ok=True,
        no_leakage=True,
        no_unknown_membership_traded=True,
        risk_config_valid=True,
        execution_config_valid=True,
        operator_approved_paper_session=True,
    )
    assert paper.paper_eligible is False


def test_live_eligible_false(tmp_path: Path):
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "d", dataset_version="l1"
        )
    )
    assert result.live_eligible is False
    live = LiveTradingEligibilityGate().evaluate(
        certified_eligibility="development_only",
        research_accepted=True,
        acceptance_evidence_id="a",
        sealed_test_ok=True,
        robustness_ok=True,
        paper_eligible=True,
        paper_evidence_id="p",
        paper_reconciliation_passed=True,
        allow_live_send=False,
    )
    assert live.live_eligible is False


def test_live_send_unavailable():
    assert list(ExecutionMode) == [ExecutionMode.DRY_RUN]


def test_real_orders_zero(tmp_path: Path):
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "d", dataset_version="o1"
        )
    )
    assert result.real_orders == 0


def test_development_campaign_cannot_create_production_acceptance():
    with pytest.raises(ValueError, match="development_only"):
        build_acceptance_record(
            campaign_id="c",
            strategy_id="s",
            strategy_version="1",
            dataset_id="d",
            dataset_version="v",
            config_hash="h",
            selection_criterion="validation_sharpe",
            research_eligibility="development_only",
            sealed_test_ok=True,
            robustness_ok=True,
            walkforward_ok=True,
            dsr_trial_accounting_ok=True,
        )


def test_report_never_claims_research_eligible_true(tmp_path: Path):
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "d", dataset_version="r1"
        )
    )
    assert "RESEARCH_ELIGIBLE: TRUE" not in result.report_text
    assert "Research eligible:\nFALSE" in result.report_text


def test_ingest_success_classification(tmp_path: Path):
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "d", dataset_version="s1"
        )
    )
    assert result.data_class == "DEVELOPMENT_DATA"
    assert result.research_eligibility == "development_only"
    assert result.research_eligible is False
    assert result.research_grade is False
    assert result.synthetic is False


def test_offline_file_import(tmp_path: Path):
    csv = FIXTURE / "bars" / "TCS.csv"
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=csv, output_root=tmp_path / "d", dataset_version="f1"
        )
    )
    assert result.success
    assert result.facts and result.facts.instrument_count >= 1


def test_chronology_error_detected():
    b1 = MarketBar(
        timestamp=datetime(2024, 1, 3),
        symbol="AAA",
        open=1,
        high=2,
        low=1,
        close=1.5,
        volume=1,
    )
    b2 = MarketBar(
        timestamp=datetime(2024, 1, 2),
        symbol="AAA",
        open=1,
        high=2,
        low=1,
        close=1.5,
        volume=1,
    )
    q = run_development_quality_checks([b1, b2])
    assert q.chronology_errors >= 1


def test_provider_attestation():
    a = DevelopmentDataProvider(bars=[]).attestation()
    assert a["data_class"] == "DEVELOPMENT_DATA"
    assert a["research_grade"] is False


def test_format_report_structure():
    m = build_manifest(
        dataset_id="india_eq_development",
        dataset_version="v",
        content_hash="sha256:x",
        synthetic=False,
        source="development_free_nse",
        universe_mode="CURRENT_SNAPSHOT",
        corporate_action_coverage="none",
        delisted_coverage="none",
        instrument_count=1,
        bar_count=1,
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-01-02",
        quality_pass=True,
        quality_error_count=0,
        quality_warning_count=0,
    )
    text = format_development_report(m)
    assert "DEVELOPMENT DATA REPORT" in text
    assert "Claims:\nNONE" in text


def test_yfinance_still_development_only_via_non_exchange():
    facts = _dev_facts(
        data_class="",
        source_grade="non_exchange",
        source="yfinance",
        extras={"synthetic": False},
        capability_source_bar_ok=False,
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_synthetic_still_development_only():
    facts = _dev_facts(
        data_class="",
        source_grade="synthetic",
        extras={"synthetic": True},
        capability_source_bar_ok=False,
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_manifest_forged_eligible_flags_forced_false():
    # Pydantic validators coerce eligibility flags to False
    m = DevelopmentManifest(
        dataset_id="x",
        dataset_version="v",
        generated_at="t",
        content_hash="sha256:x",
        research_eligible=True,
        paper_eligible=True,
        live_eligible=True,
        research_grade=True,
        exchange_authority=True,
    )
    assert m.research_eligible is False
    assert m.paper_eligible is False
    assert m.live_eligible is False
    assert m.research_grade is False
    assert m.exchange_authority is False


def test_storage_not_in_research_package_path(tmp_path: Path):
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "development", dataset_version="st1"
        )
    )
    assert "development" in str(result.root)
    assert "QUANTFUND_RESEARCH_PACKAGE" not in str(result.root)


def test_missing_sessions_note_in_facts(tmp_path: Path):
    """PIT unavailable ⇒ unknown membership sessions > 0 on facts."""
    result = ingest_development_data(
        DevelopmentIngestConfig(
            file_path=FIXTURE, output_root=tmp_path / "d", dataset_version="ms1"
        )
    )
    assert result.facts is not None
    assert result.facts.unknown_membership_session_count > 0


def test_experiment_config_records_data_class():
    from quantfund.research.experiment import ExperimentConfig

    cfg = ExperimentConfig(
        strategy_id="s",
        strategy_version="1",
        dataset_id="india_eq_development",
        dataset_version="v1",
        universe_id="dev",
        universe_version="current_snapshot",
        cost_model="zero",
        slippage_model="zero",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        start_date="2024-01-02",
        end_date="2024-01-10",
        initial_capital=100_000.0,
        research_eligibility="development_only",
        data_class="DEVELOPMENT_DATA",
    )
    assert cfg.data_class == "DEVELOPMENT_DATA"
    assert "data_class" in cfg.canonical_dict()
    assert cfg.canonical_dict()["data_class"] == "DEVELOPMENT_DATA"


def test_count_at_least_thirty():
    """Guardrail: this module must keep a broad safety net."""
    import tests.unit.test_development_data_pipeline as mod

    tests = [n for n in dir(mod) if n.startswith("test_")]
    assert len(tests) >= 30

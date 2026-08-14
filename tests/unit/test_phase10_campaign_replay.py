"""Phase 10 — campaign acceptance wiring, replay refs, extra coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quantfund.paper.eligibility import PaperEligibilityGate
from quantfund.paper.models import SessionMode
from quantfund.research.acceptance import AcceptanceDecision, CampaignAcceptancePolicy
from quantfund.research.acceptance_record import (
    build_acceptance_record_from_campaign_decision,
    verify_acceptance_record,
)
from quantfund.research.backtest_paper_compare import compare_backtest_paper
from quantfund.research.campaign import AcceptancePolicy, CampaignPurpose
from quantfund.research.campaign_state import CandidateState
from quantfund.research.candidate_pool import CandidateRecord
from quantfund.research.drift import DriftPolicyV1, evaluate_drift
from quantfund.research.paper_evidence import build_paper_evidence_from_session
from quantfund.research.paper_policy import PaperPolicyV1, evaluate_paper_policy
from quantfund.research.paper_session_fsm import PaperSessionFSM, PaperValidationState
from quantfund.research.test_seal import CampaignTestSeal
from quantfund.paper.eligibility import PaperEligibilityDecision
from quantfund.paper.reconciliation import ReconciliationReport
from quantfund.paper.session import PaperSessionResult


def _seal(*, sealed: bool = True) -> CampaignTestSeal:
    s = CampaignTestSeal(
        campaign_id="c",
        config_hash="h",
        selection_criterion="validation_sharpe",
        score_policy_version="score_policy_v1",
        dataset_id="d",
        dataset_version="v1",
        acceptance_policy_id="acceptance_policy_v1",
        sealed=sealed,
        test_evaluation_log=["cand1"] if sealed else [],
    )
    return s


def _cand(**kw):
    base = dict(
        candidate_id="cand1",
        campaign_id="camp",
        spec=None,
        strategy_hash="sh",
        state=CandidateState.TEST_EVALUATED,
        genealogy={},
        test_evaluations=1,
        metrics={
            "score": {"accepted": True, "score": 1.0, "dsr": 0.4},
            "robustness_summary": {"pass_rate": 0.9, "fragile": False},
            "walkforward_stats": {"fraction_positive_windows": 0.7},
            "test": {"sharpe": 1.0},
            "validation": {"sharpe": 0.9},
        },
    )
    base.update(kw)
    return CandidateRecord(**base)


def test_campaign_policy_rejects_development():
    d = CampaignAcceptancePolicy(AcceptancePolicy()).decide(
        candidate=_cand(),
        purpose=CampaignPurpose.RESEARCH,
        certified_eligibility="development_only",
        seal=_seal(),
        robustness_pass_rate=0.9,
        robustness_fragile=False,
        walkforward_enabled=False,
        walkforward_stats=None,
        score_accepted=True,
        score_rejection_reasons=None,
        trial_counts={"n_experiments": 3},
    )
    assert d.accepted is False


def test_campaign_policy_accepts_research_eligible_path():
    d = CampaignAcceptancePolicy(AcceptancePolicy()).decide(
        candidate=_cand(),
        purpose=CampaignPurpose.RESEARCH,
        certified_eligibility="research_eligible",
        seal=_seal(),
        robustness_pass_rate=0.9,
        robustness_fragile=False,
        walkforward_enabled=True,
        walkforward_stats={"fraction_positive_windows": 0.7, "median_window_sharpe": 0.5},
        score_accepted=True,
        score_rejection_reasons=None,
        trial_counts={"n_experiments": 3},
    )
    assert d.accepted is True


def test_build_record_from_campaign_decision():
    rec = build_acceptance_record_from_campaign_decision(
        campaign_id="camp",
        config_hash="cfg",
        dataset_id="ds",
        dataset_version="v1",
        selection_criterion="validation_sharpe",
        research_eligibility="research_eligible",
        candidate_id="cand1",
        strategy_id="s",
        strategy_version="1.0.0",
        strategy_hash="sh",
        experiment_id="exp1",
        metrics=_cand().metrics,
        sealed_test_ok=True,
        n_trials=4,
    )
    assert verify_acceptance_record(rec) == []
    assert rec.dsr == 0.4


def test_rejected_on_feature_leakage_gate():
    d = CampaignAcceptancePolicy(AcceptancePolicy()).decide(
        candidate=_cand(),
        purpose=CampaignPurpose.RESEARCH,
        certified_eligibility="research_eligible",
        seal=_seal(),
        robustness_pass_rate=1.0,
        robustness_fragile=False,
        walkforward_enabled=False,
        walkforward_stats=None,
        score_accepted=True,
        score_rejection_reasons=None,
        trial_counts={"n_experiments": 1},
        feature_leakage=True,
    )
    assert d.accepted is False
    assert "feature_leakage" in d.reasons


def test_rejected_unknown_membership_traded():
    d = CampaignAcceptancePolicy(AcceptancePolicy()).decide(
        candidate=_cand(),
        purpose=CampaignPurpose.RESEARCH,
        certified_eligibility="research_eligible",
        seal=_seal(),
        robustness_pass_rate=1.0,
        robustness_fragile=False,
        walkforward_enabled=False,
        walkforward_stats=None,
        score_accepted=True,
        score_rejection_reasons=None,
        trial_counts={"n_experiments": 1},
        unknown_membership_traded=True,
    )
    assert d.accepted is False


def test_test_seal_required():
    d = CampaignAcceptancePolicy(AcceptancePolicy()).decide(
        candidate=_cand(),
        purpose=CampaignPurpose.RESEARCH,
        certified_eligibility="research_eligible",
        seal=_seal(sealed=False),
        robustness_pass_rate=1.0,
        robustness_fragile=False,
        walkforward_enabled=False,
        walkforward_stats=None,
        score_accepted=True,
        score_rejection_reasons=None,
        trial_counts={"n_experiments": 1},
    )
    assert d.accepted is False


def test_hash_mismatch_blocks_paper():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id="e",
        strategy_spec_hash="a",
        accepted_strategy_spec_hash="b",
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
    assert any("hash_mismatch" in b for b in d.blockers)


def test_config_refs_replayable_on_evidence():
    result = PaperSessionResult(
        session_id="sess",
        mode=SessionMode.PRODUCTION,
        paper_eligible=True,
        eligibility=PaperEligibilityDecision(
            paper_eligible=True,
            certified_eligibility="research_eligible",
            mode=SessionMode.PRODUCTION,
        ),
        orders=[],
        fills=[],
        snapshot={"initial_cash": 1.0, "equity": 1.0},
        state_hash="sha256:x",
        reconciliation=ReconciliationReport(ok=True, issues=[]),
        halted=False,
        halt_reason=None,
        audit_event_count=0,
    )
    refs = {
        "strategy_config": "cfg",
        "dataset_version": "v1",
        "feature_versions": {"mom": "1"},
        "execution_model": "next_bar_open",
        "cost_model": "equity_delivery_v1",
        "slippage_model": "fixed_bps_5",
        "risk_policy": "paper_risk_v1",
        "paper_policy": "paper_policy_v1",
        "code_version": "0.10.0",
    }
    ev = build_paper_evidence_from_session(
        result, strategy_id="s", strategy_version="1", config_refs=refs
    )
    for k in refs:
        assert ev.config_refs[k] == refs[k]


def test_fsm_failed_is_terminal():
    fsm = PaperSessionFSM("x")
    fsm.fail("bad")
    try:
        fsm.transition(PaperValidationState.PASSED)
        assert False, "should not transition"
    except Exception:
        pass


def test_turnover_limit_policy():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 100,
            "trade_count": 10,
            "max_drawdown": 0.01,
            "reconciliation_ok": True,
            "turnover": 9.0,
        },
        policy=PaperPolicyV1(max_turnover=2.0, min_session_duration_seconds=10),
    )
    assert any("turnover" in b for b in d.blockers)


def test_slippage_tolerance_policy():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 100,
            "trade_count": 10,
            "max_drawdown": 0.01,
            "reconciliation_ok": True,
            "mean_slippage_bps": 100.0,
        },
        policy=PaperPolicyV1(max_slippage_bps_mean=20.0, min_session_duration_seconds=10),
    )
    assert any("slippage" in b for b in d.blockers)


def test_compare_execution_timing_mismatch():
    c = compare_backtest_paper(
        {"execution_timing": "next_bar_open", "returns": 0.1},
        {"execution_timing": "same_bar", "returns": 0.1},
    )
    assert "execution_timing_mismatch" in c.divergence_flags


def test_drift_membership_warning():
    r = evaluate_drift(
        baseline={"universe_size": 10},
        observed={},
        membership_changes=[{"x": 1}] * 5,
        policy=DriftPolicyV1(max_membership_change_rate=0.1),
    )
    assert any(f.code == "membership_changes" for f in r.findings)


def test_acceptance_decision_to_dict():
    d = AcceptanceDecision(accepted=False, reasons=["x"], notes=["y"])
    assert d.to_dict()["accepted"] is False

"""Phase 10 — paper eligibility, policy, FSM, comparison, drift."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from quantfund.paper.eligibility import PaperEligibilityGate
from quantfund.paper.models import SessionMode
from quantfund.research.acceptance_record import build_acceptance_record
from quantfund.research.backtest_paper_compare import compare_backtest_paper
from quantfund.research.drift import DriftSeverity, evaluate_drift
from quantfund.research.paper_policy import (
    PaperPolicyV1,
    PaperPolicyVerdict,
    evaluate_paper_policy,
)
from quantfund.research.paper_session_fsm import (
    IllegalPaperSessionTransition,
    PaperSessionFSM,
    PaperValidationState,
)
from quantfund.research.promotion import (
    LiveCandidateStatus,
    evaluate_live_eligibility_candidate,
    evaluate_paper_eligibility_from_acceptance,
)


def _rec(**kw):
    base = dict(
        campaign_id="c1",
        strategy_id="s1",
        strategy_version="1.0.0",
        dataset_id="d1",
        dataset_version="v1",
        config_hash="h1",
        selection_criterion="validation_sharpe",
        research_eligibility="research_eligible",
        sealed_test_ok=True,
        robustness_ok=True,
        walkforward_ok=True,
        dsr_trial_accounting_ok=True,
        no_leakage=True,
        no_unknown_membership_traded=True,
        n_trials=5,
        dsr=0.2,
    )
    base.update(kw)
    return build_acceptance_record(**base)


def test_development_dataset_rejected_for_paper():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="development_only",
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id="x",
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
    assert d.paper_eligible is False


def test_research_dataset_with_full_gates_paper_eligible():
    rec = _rec()
    d = evaluate_paper_eligibility_from_acceptance(rec)
    assert d.paper_eligible is True


def test_non_accepted_strategy_rejected():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id=None,
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
    assert d.paper_eligible is False
    assert any("acceptance_evidence" in b for b in d.blockers)


def test_leaked_strategy_rejected():
    rec = _rec(no_leakage=False)
    d = evaluate_paper_eligibility_from_acceptance(rec)
    assert d.paper_eligible is False


def test_invalid_risk_rejected():
    rec = _rec()
    d = evaluate_paper_eligibility_from_acceptance(rec, risk_config_valid=False)
    assert d.paper_eligible is False
    assert any("risk" in b for b in d.blockers)


def test_invalid_execution_rejected():
    rec = _rec()
    d = evaluate_paper_eligibility_from_acceptance(
        rec, execution_config_valid=False
    )
    assert d.paper_eligible is False


def test_operator_required_for_paper():
    rec = _rec()
    d = evaluate_paper_eligibility_from_acceptance(
        rec, operator_approved_paper_session=False
    )
    assert d.paper_eligible is False


def test_sealed_test_required():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id="ev",
        sealed_test_ok=False,
        robustness_ok=True,
        walkforward_ok=True,
        dsr_trial_accounting_ok=True,
        no_leakage=True,
        no_unknown_membership_traded=True,
        risk_config_valid=True,
        execution_config_valid=True,
        operator_approved_paper_session=True,
    )
    assert any("sealed_test" in b for b in d.blockers)


def test_robustness_required():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id="ev",
        sealed_test_ok=True,
        robustness_ok=False,
        walkforward_ok=True,
        dsr_trial_accounting_ok=True,
        no_leakage=True,
        no_unknown_membership_traded=True,
        risk_config_valid=True,
        execution_config_valid=True,
        operator_approved_paper_session=True,
    )
    assert any("robustness" in b for b in d.blockers)


def test_walkforward_required():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id="ev",
        sealed_test_ok=True,
        robustness_ok=True,
        walkforward_ok=False,
        dsr_trial_accounting_ok=True,
        no_leakage=True,
        no_unknown_membership_traded=True,
        risk_config_valid=True,
        execution_config_valid=True,
        operator_approved_paper_session=True,
    )
    assert any("walkforward" in b for b in d.blockers)


def test_dsr_trial_required():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        session_mode=SessionMode.PRODUCTION,
        acceptance_evidence_id="ev",
        sealed_test_ok=True,
        robustness_ok=True,
        walkforward_ok=True,
        dsr_trial_accounting_ok=False,
        no_leakage=True,
        no_unknown_membership_traded=True,
        risk_config_valid=True,
        execution_config_valid=True,
        operator_approved_paper_session=True,
    )
    assert any("dsr" in b for b in d.blockers)


def test_sandbox_never_paper_eligible_even_with_record():
    rec = _rec()
    d = evaluate_paper_eligibility_from_acceptance(
        rec, session_mode=SessionMode.INFRASTRUCTURE_SANDBOX
    )
    assert d.paper_eligible is False


def test_campaign_accept_alone_insufficient():
    d = PaperEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        session_mode=SessionMode.PRODUCTION,
        campaign_accepted=True,
        acceptance_evidence_id=None,
    )
    assert d.paper_eligible is False


def test_fsm_happy_path_to_passed():
    fsm = PaperSessionFSM("s1")
    fsm.transition(PaperValidationState.ELIGIBILITY_CHECKED)
    fsm.transition(PaperValidationState.READY)
    fsm.transition(PaperValidationState.RUNNING)
    fsm.transition(PaperValidationState.RECONCILING)
    fsm.transition(PaperValidationState.COMPLETED)
    fsm.transition(PaperValidationState.EVALUATED)
    fsm.transition(PaperValidationState.PASSED)
    assert fsm.state == PaperValidationState.PASSED


def test_fsm_fail_closed_from_running():
    fsm = PaperSessionFSM("s2")
    fsm.transition(PaperValidationState.ELIGIBILITY_CHECKED)
    fsm.transition(PaperValidationState.READY)
    fsm.transition(PaperValidationState.RUNNING)
    fsm.fail("kill_switch")
    assert fsm.state == PaperValidationState.FAILED
    assert fsm.fail_reason == "kill_switch"


def test_fsm_illegal_skip():
    fsm = PaperSessionFSM("s3")
    with pytest.raises(IllegalPaperSessionTransition):
        fsm.transition(PaperValidationState.RUNNING)


def test_fsm_no_live_transition_field():
    fsm = PaperSessionFSM("s4")
    assert fsm.to_dict()["live_transition"] is False


def test_paper_policy_insufficient_duration():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 1,
            "session_count": 1,
            "trade_count": 10,
            "max_drawdown": 0.01,
            "reconciliation_ok": True,
        },
        policy=PaperPolicyV1(min_session_duration_seconds=60),
    )
    assert d.verdict == PaperPolicyVerdict.INSUFFICIENT_EVIDENCE
    assert d.live_eligibility_candidate is False


def test_paper_policy_insufficient_trades():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 120,
            "trade_count": 1,
            "max_drawdown": 0.01,
            "reconciliation_ok": True,
        },
        policy=PaperPolicyV1(min_trades=5),
    )
    assert any("insufficient_trades" in b for b in d.blockers)


def test_paper_policy_drawdown_violation():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 120,
            "trade_count": 10,
            "max_drawdown": 0.5,
            "reconciliation_ok": True,
        },
        policy=PaperPolicyV1(max_drawdown=0.2),
    )
    assert d.verdict == PaperPolicyVerdict.FAILED


def test_paper_policy_recon_failure():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 120,
            "trade_count": 10,
            "max_drawdown": 0.01,
            "reconciliation_ok": False,
            "reconciliation_failures": 1,
        }
    )
    assert any("reconciliation" in b for b in d.blockers)


def test_paper_policy_execution_failure():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 120,
            "trade_count": 10,
            "max_drawdown": 0.01,
            "reconciliation_ok": True,
            "execution_failures": 2,
        },
        policy=PaperPolicyV1(max_execution_failures=0),
    )
    assert any("execution_failures" in b for b in d.blockers)


def test_paper_policy_pass_sets_candidate():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 120,
            "session_count": 2,
            "trade_count": 10,
            "max_drawdown": 0.05,
            "reconciliation_ok": True,
        },
        policy=PaperPolicyV1(min_sessions=1, min_trades=3),
    )
    assert d.verdict == PaperPolicyVerdict.PASSED
    assert d.live_eligibility_candidate is True
    assert d.to_dict()["live_trading"] == "DISABLED"
    assert d.to_dict()["claims"] == "NONE"


def test_paper_policy_divergence_blocks():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 120,
            "trade_count": 10,
            "max_drawdown": 0.01,
            "reconciliation_ok": True,
        },
        comparison={"material_divergence": True, "divergence_flags": ["sharpe"]},
    )
    assert any("divergence" in b for b in d.blockers)


def test_compare_flags_material_divergence():
    c = compare_backtest_paper(
        {"returns": 0.2, "sharpe": 2.0, "trade_count": 100},
        {"returns": -0.1, "sharpe": 0.1, "trade_count": 10},
    )
    assert c.material_divergence is True
    assert c.to_dict()["live_eligible_from_pnl_alone"] is False


def test_compare_aligned_no_flags():
    m = {
        "returns": 0.1,
        "sharpe": 1.0,
        "max_drawdown": 0.05,
        "turnover": 1.0,
        "trade_count": 20,
        "win_rate": 0.5,
        "average_trade": 10.0,
        "transaction_costs": 5.0,
        "slippage": 2.0,
        "exposure": 0.5,
        "signal_frequency": 0.2,
        "execution_timing": "next_bar_open",
        "missed_fills": 0,
        "rejected_orders": 0,
    }
    c = compare_backtest_paper(m, dict(m))
    assert c.material_divergence is False


def test_drift_missing_features_hard_fail():
    r = evaluate_drift(
        baseline={"turnover": 1.0},
        observed={"missing_feature_rate": 0.5},
    )
    assert r.severity == DriftSeverity.HARD_FAIL
    assert r.strategy_modified is False


def test_drift_feature_z_warning():
    r = evaluate_drift(
        baseline={},
        observed={"feature_mean_z": {"mom": 5.0}},
    )
    assert r.severity == DriftSeverity.WARNING


def test_drift_data_gaps_hard_fail():
    r = evaluate_drift(baseline={}, observed={}, data_gaps=3)
    assert r.severity == DriftSeverity.HARD_FAIL


def test_drift_never_modifies_strategy():
    r = evaluate_drift(
        baseline={"turnover": 1, "signal_frequency": 1, "exposure": 0.2},
        observed={"turnover": 5, "signal_frequency": 5, "exposure": 0.9},
        membership_changes=[{"sym": "A"}],
        corporate_action_events=[{"handled": False}],
    )
    assert r.strategy_modified is False


def test_live_candidate_blocked_without_evidence():
    status, blockers = evaluate_live_eligibility_candidate(
        certified_eligibility="research_eligible",
        acceptance=_rec(),
        paper_eligible=True,
        paper_evidence=None,
        paper_policy=None,
    )
    assert status == LiveCandidateStatus.BLOCKED
    assert blockers

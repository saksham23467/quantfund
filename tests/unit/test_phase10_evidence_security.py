"""Phase 10 — paper evidence, reconciliation, security, promotion."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantfund.execution.broker_adapter import ALLOWED_BROKER_ADAPTER_IDS, assert_mock_only
from quantfund.execution.gateway import ExecutionMode
from quantfund.execution.live_eligibility import LiveTradingEligibilityGate
from quantfund.paper.eligibility import PaperEligibilityDecision
from quantfund.paper.models import SessionMode
from quantfund.paper.reconciliation import ReconciliationReport, reconcile_paper_state
from quantfund.paper.portfolio import PaperPortfolio
from quantfund.paper.session import PaperSessionResult
from quantfund.research.acceptance_record import build_acceptance_record
from quantfund.research.paper_evidence import (
    aggregate_paper_evidence,
    build_paper_evidence_from_session,
    make_paper_evidence_id,
    verify_paper_evidence,
    write_paper_evidence,
)
from quantfund.research.paper_policy import PaperPolicyV1, evaluate_paper_policy
from quantfund.research.paper_report import (
    build_paper_validation_report,
    format_paper_validation_summary,
)
from quantfund.research.promotion import (
    LiveCandidateStatus,
    evaluate_live_eligibility_candidate,
    evaluate_paper_eligibility_from_acceptance,
    run_phase10_pipeline_from_package,
    run_phase10_pipeline_synthetic,
)
from quantfund.trading.models import Fill, OrderSide


def _rec():
    return build_acceptance_record(
        campaign_id="c",
        strategy_id="s",
        strategy_version="1",
        dataset_id="d",
        dataset_version="v",
        config_hash="h",
        selection_criterion="validation_sharpe",
        research_eligibility="research_eligible",
        sealed_test_ok=True,
        robustness_ok=True,
        walkforward_ok=True,
        dsr_trial_accounting_ok=True,
        no_leakage=True,
        no_unknown_membership_traded=True,
        n_trials=3,
    )


def _session_result(*, recon_ok: bool = True, fills: list | None = None):
    from quantfund.paper.reconciliation import ReconciliationReport

    return PaperSessionResult(
        session_id="sess1",
        mode=SessionMode.PRODUCTION,
        paper_eligible=True,
        eligibility=PaperEligibilityDecision(
            paper_eligible=True,
            certified_eligibility="research_eligible",
            mode=SessionMode.PRODUCTION,
        ),
        orders=[{"order_id": "o1"}],
        fills=fills or [],
        snapshot={"initial_cash": 100_000.0, "equity": 100_000.0, "cash": 100_000.0},
        state_hash="sha256:abc",
        reconciliation=ReconciliationReport(ok=recon_ok, issues=[]),
        halted=False,
        halt_reason=None,
        audit_event_count=5,
    )


def test_build_paper_evidence_metrics():
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    end = start + timedelta(seconds=300)
    ev = build_paper_evidence_from_session(
        _session_result(),
        strategy_id="s",
        strategy_version="1",
        start_time=start,
        end_time=end,
        acceptance_evidence_id="ae",
        equity_curve=[100_000, 101_000, 99_000],
        config_refs={
            "cost_model": "equity_delivery_v1",
            "slippage_model": "fixed_bps_5",
            "paper_policy": "paper_policy_v1",
        },
    )
    assert ev.duration_seconds == 300
    assert ev.max_drawdown > 0
    assert ev.reconciliation_ok is True
    assert ev.config_refs["paper_policy"] == "paper_policy_v1"


def test_paper_evidence_id_deterministic():
    a = make_paper_evidence_id(
        session_id="s", strategy_id="a", strategy_version="1", state_hash_value="h"
    )
    b = make_paper_evidence_id(
        session_id="s", strategy_id="a", strategy_version="1", state_hash_value="h"
    )
    assert a == b


def test_verify_paper_evidence_recon_fail():
    ev = build_paper_evidence_from_session(
        _session_result(recon_ok=False),
        strategy_id="s",
        strategy_version="1",
    )
    assert "reconciliation_failed" in verify_paper_evidence(ev)


def test_aggregate_multi_session():
    ev1 = build_paper_evidence_from_session(
        _session_result(), strategy_id="s", strategy_version="1"
    )
    r2 = PaperSessionResult(
        session_id="sess2",
        mode=SessionMode.PRODUCTION,
        paper_eligible=True,
        eligibility=PaperEligibilityDecision(
            paper_eligible=True,
            certified_eligibility="research_eligible",
            mode=SessionMode.PRODUCTION,
        ),
        orders=[],
        fills=[],
        snapshot={"initial_cash": 100_000.0, "equity": 100_000.0},
        state_hash="sha256:def",
        reconciliation=ReconciliationReport(ok=True, issues=[]),
        halted=False,
        halt_reason=None,
        audit_event_count=1,
    )
    ev2 = build_paper_evidence_from_session(
        r2, strategy_id="s", strategy_version="1"
    )
    # mutate trade counts via policy metrics
    agg = aggregate_paper_evidence([ev1, ev2])
    assert agg["session_count"] == 2
    assert agg["reconciliation_ok"] is True


def test_write_paper_evidence(tmp_path: Path):
    ev = build_paper_evidence_from_session(
        _session_result(), strategy_id="s", strategy_version="1"
    )
    path = write_paper_evidence(tmp_path / "e.json", ev)
    assert path.exists()


def test_reconcile_duplicate_fills():
    book = PaperPortfolio.create(10_000)
    f = Fill(
        fill_id="f1",
        order_id="o1",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=1,
        price=100,
        slippage_per_unit=0,
        transaction_cost=0,
        gross_value=100,
        net_cash_delta=-100,
    )
    # apply once
    book.apply_fill(f)
    report = reconcile_paper_state(
        book, fills=[f, f], initial_cash=10_000
    )
    assert report.ok is False
    assert any(i.code == "duplicate_fill" for i in report.issues)


def test_reconcile_orphan_fill():
    book = PaperPortfolio.create(10_000)
    f = Fill(
        fill_id="f1",
        order_id="missing",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=1,
        price=100,
        slippage_per_unit=0,
        transaction_cost=0,
        gross_value=100,
        net_cash_delta=-100,
    )
    book.apply_fill(f)
    report = reconcile_paper_state(
        book,
        fills=[f],
        initial_cash=10_000,
        known_order_ids={"other"},
    )
    assert any(i.code == "orphan_fill" for i in report.issues)


def test_reconcile_missing_audit_fills():
    book = PaperPortfolio.create(10_000)
    f = Fill(
        fill_id="f1",
        order_id="o1",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=1,
        price=100,
        slippage_per_unit=0,
        transaction_cost=0,
        gross_value=100,
        net_cash_delta=-100,
    )
    book.apply_fill(f)
    report = reconcile_paper_state(
        book,
        fills=[f],
        initial_cash=10_000,
        audit_fill_ids=set(),
    )
    assert any(i.code == "missing_fills_in_audit" for i in report.issues)


def test_reconcile_ok_with_matching_audit():
    book = PaperPortfolio.create(10_000)
    f = Fill(
        fill_id="f1",
        order_id="o1",
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=1,
        price=100,
        slippage_per_unit=0,
        transaction_cost=0,
        gross_value=100,
        net_cash_delta=-100,
    )
    book.apply_fill(f)
    report = reconcile_paper_state(
        book,
        fills=[f],
        initial_cash=10_000,
        known_order_ids={"o1"},
        audit_fill_ids={"f1"},
    )
    assert report.ok is True


def test_no_live_activation_in_promotion():
    snap = run_phase10_pipeline_synthetic()
    assert snap.live_eligible is False
    assert snap.real_orders == 0


def test_only_mock_broker_allowed():
    assert "mock" in ALLOWED_BROKER_ADAPTER_IDS or "mock_broker" in {
        x.lower() for x in ALLOWED_BROKER_ADAPTER_IDS
    }
    with pytest.raises(ValueError):
        assert_mock_only("zerodha")


def test_execution_mode_dry_run_only():
    assert list(ExecutionMode) == [ExecutionMode.DRY_RUN]


def test_live_gate_still_blocks_send_flag():
    d = LiveTradingEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        research_accepted=True,
        acceptance_evidence_id="a",
        sealed_test_ok=True,
        robustness_ok=True,
        paper_eligible=True,
        paper_evidence_id="p",
        paper_reconciliation_passed=True,
        allow_live_send=True,
    )
    assert d.live_eligible is False


def test_strategy_modules_do_not_import_execution():
    import quantfund.strategies.base as base

    src = inspect.getsource(base)
    assert "quantfund.execution" not in src
    assert "MockBroker" not in src


def test_acceptance_record_has_no_credentials():
    rec = _rec()
    blob = str(rec.to_dict())
    assert "api_key" not in blob.lower()
    assert "password" not in blob.lower()
    assert "secret" not in blob.lower()


def test_paper_evidence_policy_integration():
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    ev = build_paper_evidence_from_session(
        _session_result(),
        strategy_id="s",
        strategy_version="1",
        start_time=start,
        end_time=start + timedelta(seconds=600),
        equity_curve=[100_000, 100_500, 100_200],
    )
    # bump trade_count for policy via aggregate override
    metrics = ev.evidence_metrics_for_policy()
    metrics["trade_count"] = 10
    metrics["duration_seconds"] = 600
    d = evaluate_paper_policy(metrics, policy=PaperPolicyV1(min_trades=3))
    assert d.verdict.value == "PASSED"


def test_live_candidate_full_path():
    rec = _rec()
    assert evaluate_paper_eligibility_from_acceptance(rec).paper_eligible
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    ev = build_paper_evidence_from_session(
        _session_result(),
        strategy_id="s",
        strategy_version="1",
        start_time=start,
        end_time=start + timedelta(seconds=600),
        equity_curve=[100_000, 100_100],
    )
    metrics = ev.evidence_metrics_for_policy()
    metrics["trade_count"] = 10
    metrics["duration_seconds"] = 600
    policy = evaluate_paper_policy(metrics, policy=PaperPolicyV1(min_trades=3))
    # For candidate gate, reconciliation must verify — our ev is ok
    # But trade_count on record is 0 — verify_paper_evidence only checks recon/id
    status, blockers = evaluate_live_eligibility_candidate(
        certified_eligibility="research_eligible",
        acceptance=rec,
        paper_eligible=True,
        paper_evidence=ev,
        paper_policy=policy,
    )
    assert status == LiveCandidateStatus.LIVE_ELIGIBILITY_CANDIDATE
    assert blockers == []


def test_package_pipeline_without_env_stays_dev():
    # Explicit None package
    snap = run_phase10_pipeline_from_package(None)
    assert snap.research_eligibility == "development_only"
    assert snap.paper_eligible is False
    assert snap.real_orders == 0


def test_report_summary_contains_safety_lines():
    payload = build_paper_validation_report(
        research_eligibility="development_only",
        paper_eligible=False,
        accepted_strategies=[],
        paper_sessions=[],
        paper_policy={"verdict": "NOT_RUN"},
        real_orders=0,
        claims="NONE",
    )
    text = format_paper_validation_summary(payload)
    assert "DEVELOPMENT_ONLY" in text
    assert "Phase 11 has NOT started" in text
    assert "Real orders: 0" in text


def test_positive_pnl_insufficient_note_in_compare():
    from quantfund.research.backtest_paper_compare import compare_backtest_paper

    c = compare_backtest_paper({"returns": 0.01}, {"returns": 0.5})
    assert "paper_pnl_positive_insufficient_for_live" in c.notes


def test_kill_switch_incident_fails_policy():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 120,
            "trade_count": 10,
            "max_drawdown": 0.01,
            "reconciliation_ok": True,
            "kill_switch_incidents": 1,
        },
        policy=PaperPolicyV1(max_kill_switch_incidents=0),
    )
    assert d.verdict.value == "FAILED"


def test_data_quality_incident_fails_policy():
    d = evaluate_paper_policy(
        {
            "duration_seconds": 120,
            "trade_count": 10,
            "max_drawdown": 0.01,
            "reconciliation_ok": True,
            "data_quality_incidents": 2,
        }
    )
    assert any("data_quality" in b for b in d.blockers)


def test_no_network_order_path_in_research_promotion():
    import quantfund.research.promotion as promo

    src = inspect.getsource(promo)
    assert "import requests" not in src
    assert "import httpx" not in src
    assert "urllib.request" not in src
    assert "socket." not in src
    assert "allow_live_send=True" not in src

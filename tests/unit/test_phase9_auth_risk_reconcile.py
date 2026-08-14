"""Phase 9 — authorization ladder, capital, kill switch, reconcile, audit."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantfund.execution.credentials import redact_secrets
from quantfund.execution.gateway import ExecutionGateway, ExecutionMode, GatewayConfig
from quantfund.execution.live_eligibility import LiveAuthorization, LiveTradingEligibilityGate
from quantfund.execution.live_orders import BrokerOrderState, IdempotencyRecord
from quantfund.execution.live_risk import (
    PLATFORM_SAFETY_LIMITS,
    CapitalLimits,
    LiveRiskEngine,
    merge_capital_limits,
)
from quantfund.execution.mock_broker import MockBehavior
from quantfund.execution.operator_approval import OperatorApprovalGate
from quantfund.execution.reconciliation_live import reconcile_live_state
from quantfund.execution.broker_adapter import (
    BrokerCashView,
    BrokerOrderView,
    BrokerReconcileSnapshot,
)
from quantfund.paper.kill_switch import KillSwitch
from quantfund.trading.models import Order, OrderSide, OrderType


def _order(qty: float = 10.0) -> Order:
    return Order(
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=qty,
        order_type=OrderType.MARKET,
    )


def test_development_only_live_blocked():
    d = LiveTradingEligibilityGate().evaluate(
        certified_eligibility="development_only",
        research_accepted=True,
        acceptance_evidence_id="a",
        sealed_test_ok=True,
        robustness_ok=True,
        paper_eligible=True,
        paper_evidence_id="p",
        paper_reconciliation_passed=True,
    )
    assert d.authorization == LiveAuthorization.LIVE_BLOCKED
    assert d.live_eligible is False


def test_research_accept_alone_insufficient():
    d = LiveTradingEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        research_accepted=True,
        acceptance_evidence_id=None,
        sealed_test_ok=True,
        robustness_ok=True,
        paper_eligible=True,
        paper_evidence_id="p",
        paper_reconciliation_passed=True,
    )
    assert d.live_eligible is False
    assert any("acceptance_evidence" in b for b in d.blockers)


def test_paper_eligible_alone_insufficient():
    d = LiveTradingEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        research_accepted=True,
        acceptance_evidence_id="a",
        sealed_test_ok=True,
        robustness_ok=True,
        paper_eligible=True,
        paper_evidence_id=None,
        paper_reconciliation_passed=True,
    )
    assert d.live_eligible is False
    assert any("paper_evidence" in b for b in d.blockers)


def test_real_broker_blocked_in_gate():
    d = LiveTradingEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        research_accepted=True,
        acceptance_evidence_id="a",
        sealed_test_ok=True,
        robustness_ok=True,
        paper_eligible=True,
        paper_evidence_id="p",
        paper_reconciliation_passed=True,
        broker_adapter_id="zerodha",
    )
    assert any("real_broker" in b for b in d.blockers)


def test_live_send_flag_blocked():
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
    assert any("live_send_disabled" in b for b in d.blockers)


def test_full_ladder_would_authorize_without_live_send():
    d = LiveTradingEligibilityGate().evaluate(
        certified_eligibility="research_eligible",
        research_accepted=True,
        acceptance_evidence_id="a",
        sealed_test_ok=True,
        robustness_ok=True,
        paper_eligible=True,
        paper_evidence_id="p",
        paper_reconciliation_passed=True,
        allow_live_send=False,
    )
    assert d.live_eligible is True
    assert d.authorization == LiveAuthorization.LIVE_AUTHORIZED


def test_operator_approval_required():
    gw = ExecutionGateway(
        GatewayConfig(
            session_id="op1",
            mode=ExecutionMode.DRY_RUN,
            certified_eligibility="research_eligible",
            research_accepted=True,
            acceptance_evidence_id="a",
            sealed_test_ok=True,
            robustness_ok=True,
            paper_eligible=True,
            paper_evidence_id="p",
            paper_reconciliation_passed=True,
        )
    )
    gw.start()
    assert gw.eligibility is not None and gw.eligibility.live_eligible
    res = gw.submit_order(_order(1), intent_id="i", ref_price=10)
    assert res.reason == "operator_approval_required"
    gw.approve_operator(operator_id="human_ops", reason="approved for dry_run test")
    res2 = gw.submit_order(_order(1), intent_id="i2", ref_price=10)
    assert res2.accepted is True


def test_ai_operator_forbidden():
    gate = OperatorApprovalGate()
    with pytest.raises(ValueError, match="ai_operator"):
        gate.approve(session_id="s", operator_id="ai", reason="nope")


def test_capital_hierarchy_tightens():
    strategy = CapitalLimits(100, 100, 100, max_capital_allocation=100)
    session = CapitalLimits(80, 80, 80, max_capital_allocation=80)
    account = CapitalLimits(90, 90, 90, max_capital_allocation=90)
    merged = merge_capital_limits(strategy, session, account, PLATFORM_SAFETY_LIMITS)
    assert merged.max_order_notional == 80
    assert merged.max_capital_allocation == 80


def test_strategy_cannot_raise_above_platform():
    eng = LiveRiskEngine(
        strategy_limits=CapitalLimits(1_000_000, 1_000_000, 1_000_000),
        session_limits=CapitalLimits(1_000_000, 1_000_000, 1_000_000),
        account_limits=CapitalLimits(1_000_000, 1_000_000, 1_000_000),
        platform_limits=PLATFORM_SAFETY_LIMITS,
    )
    assert eng.effective.max_order_notional <= PLATFORM_SAFETY_LIMITS.max_order_notional


def test_capital_limit_rejects_order():
    gw = ExecutionGateway(
        GatewayConfig(
            session_id="cap1",
            strategy_limits=CapitalLimits(50, 50, 50, max_capital_allocation=50),
            session_limits=CapitalLimits(50, 50, 50, max_capital_allocation=50),
            account_limits=CapitalLimits(50, 50, 50, max_capital_allocation=50),
        )
    )
    gw.start()
    res = gw.submit_order(
        _order(10),
        intent_id="c",
        ref_price=100,
        require_live_authorized=False,
        require_operator=False,
    )
    assert res.accepted is False
    assert res.reason == "max_order_notional"


def test_kill_switch_freeze_only():
    gw = ExecutionGateway(GatewayConfig(session_id="ks1"))
    gw.start()
    gw.activate_kill_switch(reason="manual", actor="op")
    res = gw.submit_order(
        _order(1),
        intent_id="k",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    assert res.reason == "kill_switch"
    assert "kill_switch_activated" in gw.audit.event_types()
    # No flatten API invoked — positions unchanged
    assert gw.internal_positions == {}


def test_authorization_blocks_without_force():
    gw = ExecutionGateway(GatewayConfig(session_id="auth1"))
    gw.start()
    res = gw.submit_order(_order(1), intent_id="a", ref_price=10)
    assert res.reason == "live_authorization_blocked"


def test_reconcile_pass_after_fill():
    gw = ExecutionGateway(GatewayConfig(session_id="rc1"))
    gw.start()
    gw.submit_order(
        _order(2),
        intent_id="r",
        ref_price=100,
        require_live_authorized=False,
        require_operator=False,
    )
    report = gw.reconcile()
    assert report.ok is True


def test_reconcile_filled_vs_unknown():
    snap = BrokerReconcileSnapshot(
        positions=[],
        cash=BrokerCashView(cash=100_000),
        open_orders=[
            BrokerOrderView(
                client_order_id="c1",
                symbol="AAA",
                side=OrderSide.BUY,
                quantity=1,
                state=BrokerOrderState.UNKNOWN,
            )
        ],
    )
    report = reconcile_live_state(
        internal_records=[
            IdempotencyRecord(
                client_order_id="c1",
                intent_id="i",
                session_id="s",
                state=BrokerOrderState.FILLED,
                filled_quantity=1,
            )
        ],
        broker_snapshot=snap,
        internal_positions={"AAA": 1},
        internal_cash=99_900,
    )
    assert report.ok is False
    assert any(i.code == "filled_vs_unknown" for i in report.issues)


def test_reconcile_open_vs_cancelled():
    snap = BrokerReconcileSnapshot(
        positions=[],
        cash=BrokerCashView(cash=100_000),
        open_orders=[
            BrokerOrderView(
                client_order_id="c1",
                symbol="AAA",
                side=OrderSide.BUY,
                quantity=1,
                state=BrokerOrderState.CANCELLED,
            )
        ],
    )
    report = reconcile_live_state(
        internal_records=[
            IdempotencyRecord(
                client_order_id="c1",
                intent_id="i",
                session_id="s",
                state=BrokerOrderState.ACKNOWLEDGED,
            )
        ],
        broker_snapshot=snap,
        internal_positions={},
        internal_cash=100_000,
    )
    assert any(i.code == "open_vs_cancelled" for i in report.issues)


def test_reconcile_position_mismatch():
    snap = BrokerReconcileSnapshot(
        positions=[],
        cash=BrokerCashView(cash=100_000),
        open_orders=[],
    )
    report = reconcile_live_state(
        internal_records=[],
        broker_snapshot=snap,
        internal_positions={"AAA": 5},
        internal_cash=100_000,
    )
    assert any(i.code == "position_mismatch" for i in report.issues)


def test_audit_has_eligibility_events():
    gw = ExecutionGateway(GatewayConfig(session_id="aud1"))
    gw.start()
    types = gw.audit.event_types()
    assert "eligibility_check" in types
    assert "authorization_denied" in types
    assert "live_session_started" in types


def test_audit_redacts_secrets():
    payload = {"api_key": "SECRET123", "order_id": "x"}
    red = redact_secrets(payload)
    assert red["api_key"] == "***REDACTED***"
    assert red["order_id"] == "x"


def test_strategy_base_no_execution_broker_import():
    import inspect

    import quantfund.strategies.base as base

    src = inspect.getsource(base)
    assert "quantfund.execution" not in src
    assert "MockBroker" not in src
    assert "BrokerAdapter" not in src


def test_paper_adapter_still_owns_paper_fills():
    import quantfund.paper.execution as pe

    assert hasattr(pe, "PaperExecutionAdapter")


def test_kill_switch_no_auto_flatten_method():
    ks = KillSwitch()
    ks.activate(reason="x", actor="y")
    assert not hasattr(ks, "flatten")
    assert not hasattr(ks, "emergency_liquidate")


def test_gateway_stop_reports_zero_real_orders():
    gw = ExecutionGateway(GatewayConfig(session_id="stop1"))
    gw.start()
    summary = gw.stop()
    assert summary["real_orders_sent"] == 0
    assert summary["broker"] == "mock"
    assert summary["live_eligible"] is False

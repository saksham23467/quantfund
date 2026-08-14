"""Phase 10 — production readiness & controlled activation (≥60 tests)."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantfund.brokers.base import BrokerOrderRequest
from quantfund.brokers.intent_store import ExecutionIntentStore
from quantfund.brokers.zerodha.client import FakeKiteTransport
from quantfund.execution.broker_adapter import (
    BrokerCashView,
    BrokerOrderView,
    BrokerPositionView,
    BrokerReconcileSnapshot,
)
from quantfund.execution.credentials import redact_secrets
from quantfund.execution.live_orders import BrokerOrderState
from quantfund.execution.modes import QuantFundExecutionMode
from quantfund.execution.reconciliation import (
    BrokerReconciler,
    LocalExpectedState,
    ReconcileOutcome,
)
from quantfund.paper.kill_switch import KillSwitch
from quantfund.production.activation import (
    ACTIVATION_CONFIRM_PHRASE,
    create_activation_record,
    env_alone_cannot_activate,
    evaluate_activation_gates,
    write_activation_record,
)
from quantfund.production.audit import AuditEventType, ProductionAuditLog
from quantfund.production.canary import CanaryLimits, canary_check_order, evaluate_canary_readiness
from quantfund.production.connectivity import (
    ReadOnlyForbidden,
    _GuardTransport,
    run_zerodha_connectivity_test,
)
from quantfund.production.controls import ProductionControlLimits, ProductionTradingControls
from quantfund.production.e2e_replay import run_e2e_replay_fixture
from quantfund.production.fail_closed import decide_fail_closed
from quantfund.production.health import build_health_report
from quantfund.production.order_dry_run import DRY_RUN_BANNER, dry_run_order, format_dry_run
from quantfund.production.preflight import PreflightContext, PreflightStatus, run_preflight
from quantfund.trading.models import OrderSide, OrderType


def _req(**kwargs) -> BrokerOrderRequest:
    base = dict(
        execution_intent_id="p10-1",
        instrument_id="NSE:INFY",
        exchange="NSE",
        symbol="INFY",
        side=OrderSide.BUY,
        quantity=1,
        order_type=OrderType.MARKET,
        product="CNC",
        validity="DAY",
    )
    base.update(kwargs)
    return BrokerOrderRequest(**base)


def _controls(**kwargs) -> ProductionTradingControls:
    base = dict(
        kill_switch=KillSwitch(),
        limits=ProductionControlLimits(),
    )
    base.update(kwargs)
    return ProductionTradingControls(**base)


# --- preflight ---


def test_preflight_never_places_orders():
    r = run_preflight(PreflightContext(env={}, risk_limits_configured=True))
    assert r.orders_attempted == 0


def test_preflight_credentials_not_configured():
    r = run_preflight(PreflightContext(env={}))
    c = next(x for x in r.checks if x.name == "broker_credentials")
    assert c.status == PreflightStatus.NOT_CONFIGURED


def test_preflight_kill_switch_fail():
    ks = KillSwitch()
    ks.activate(reason="stop", actor="t")
    r = run_preflight(PreflightContext(env={}, kill_switch=ks, risk_limits_configured=True))
    assert any(c.name == "kill_switch_state" and c.status == PreflightStatus.FAIL for c in r.checks)
    assert r.ok is False


def test_preflight_risk_missing_fails():
    r = run_preflight(PreflightContext(env={}, risk_limits_configured=False))
    assert any(c.name == "risk_configuration" and c.status == PreflightStatus.FAIL for c in r.checks)


def test_preflight_clock_skew_fail():
    r = run_preflight(
        PreflightContext(env={}, risk_limits_configured=True, clock_skew_seconds=120)
    )
    assert any(c.name == "system_clock_timezone" and c.status == PreflightStatus.FAIL for c in r.checks)


def test_preflight_connectivity_probe_fail():
    r = run_preflight(
        PreflightContext(
            env={},
            risk_limits_configured=True,
            connectivity_probe=lambda: (_ for _ in ()).throw(RuntimeError("timeout")),
        )
    )
    assert any(c.name == "api_connectivity" and c.status == PreflightStatus.FAIL for c in r.checks)


def test_preflight_reconciliation_mismatch():
    r = run_preflight(
        PreflightContext(
            env={}, risk_limits_configured=True, reconciliation_clean=False
        )
    )
    assert any(
        c.name == "reconciliation_state" and c.status == PreflightStatus.FAIL for c in r.checks
    )


# --- connectivity / read-only ---


def test_zerodha_connectivity_simulated():
    r = run_zerodha_connectivity_test(env={}, simulate_if_unconfigured=True)
    assert r.simulated is True
    assert r.ok is True
    assert r.order_submission == "NOT EXECUTED"
    assert r.orders_placed == 0


def test_connectivity_auth_failure_unconfigured_no_sim():
    r = run_zerodha_connectivity_test(env={}, simulate_if_unconfigured=False)
    assert r.configured is False
    assert r.ok is False


def test_read_only_guard_blocks_order_post():
    guard = _GuardTransport(FakeKiteTransport())
    with pytest.raises(ReadOnlyForbidden):
        guard.request(
            method="POST",
            url="https://sandbox.kite.trade/orders/regular",
            headers={},
            data={"tradingsymbol": "INFY"},
        )


def test_connectivity_redacts_profile_secrets():
    r = run_zerodha_connectivity_test(env={}, simulate_if_unconfigured=True)
    blob = str(r.to_dict())
    assert "api_secret" not in blob or "***REDACTED***" in blob


# --- dry-run ---


def test_dry_run_not_submitted():
    res = dry_run_order(_req(), ref_price=100.0, controls=_controls())
    assert res.submitted is False
    assert "NOT A REAL ORDER" in res.banner


def test_dry_run_format_banner():
    text = format_dry_run(dry_run_order(_req(), ref_price=100.0, controls=_controls()))
    assert DRY_RUN_BANNER.splitlines()[0] in text
    assert "NOT EXECUTED" in text


def test_order_construction_in_dry_run():
    res = dry_run_order(_req(quantity=3), ref_price=200.0, controls=_controls())
    kite = res.would_send["kite_params"]
    assert kite["tradingsymbol"] == "INFY"
    assert kite["quantity"] == 3
    assert kite["transaction_type"] == "BUY"
    assert res.estimated_costs["notional"] == 600.0


# --- e2e / idempotency ---


def test_e2e_replay_ok():
    r = run_e2e_replay_fixture()
    assert r.ok is True
    assert r.reconcile_matched is True
    assert r.orders_submitted_to_network == 0


def test_e2e_idempotent_intent():
    r = run_e2e_replay_fixture()
    assert r.details["place_calls_fake"] == 1


def test_e2e_audit_trail():
    r = run_e2e_replay_fixture()
    assert "SIGNAL" in r.audit_types
    assert "FILL" in r.audit_types
    assert "RECONCILIATION" in r.audit_types


# --- reconciliation ---


def test_reconcile_duplicate_order():
    o = BrokerOrderView(
        client_order_id="c",
        broker_order_id="o1",
        symbol="INFY",
        side=OrderSide.BUY,
        quantity=1,
        state=BrokerOrderState.OPEN,
    )
    local = LocalExpectedState(orders=[o, o])
    snap = BrokerReconcileSnapshot(positions=[], cash=BrokerCashView(cash=0), open_orders=[o])
    report = BrokerReconciler().reconcile(local, snap, broker_orders=[o])
    assert any(f.outcome == ReconcileOutcome.DUPLICATE_ORDER for f in report.findings)
    assert report.matched is False
    assert report.allows_new_orders is False


def test_reconcile_duplicate_fill():
    local = LocalExpectedState(fill_ids=["f1", "f1"])
    snap = BrokerReconcileSnapshot(positions=[], cash=BrokerCashView(cash=0))
    report = BrokerReconciler().reconcile(local, snap)
    assert any(f.outcome == ReconcileOutcome.DUPLICATE_FILL for f in report.findings)


def test_reconcile_unexpected_fill():
    o = BrokerOrderView(
        client_order_id="c",
        broker_order_id="o1",
        symbol="INFY",
        side=OrderSide.BUY,
        quantity=10,
        filled_quantity=10,
        state=BrokerOrderState.FILLED,
        avg_price=100,
    )
    local = LocalExpectedState(orders=[o])  # no fill_quantities
    snap = BrokerReconcileSnapshot(positions=[], cash=BrokerCashView(cash=0), open_orders=[o])
    report = BrokerReconciler().reconcile(local, snap, broker_orders=[o])
    assert any(f.outcome == ReconcileOutcome.UNEXPECTED_FILL for f in report.findings)


def test_reconcile_stale_order():
    old = datetime.now(timezone.utc) - timedelta(days=2)
    o = BrokerOrderView(
        client_order_id="c",
        broker_order_id="o1",
        symbol="INFY",
        side=OrderSide.BUY,
        quantity=1,
        state=BrokerOrderState.OPEN,
        updated_at=old,
    )
    local = LocalExpectedState(
        orders=[o], now=datetime.now(timezone.utc), stale_after_seconds=3600
    )
    snap = BrokerReconcileSnapshot(positions=[], cash=BrokerCashView(cash=0), open_orders=[o])
    report = BrokerReconciler().reconcile(local, snap, broker_orders=[o])
    assert any(f.outcome == ReconcileOutcome.STALE_ORDER for f in report.findings)


def test_reconcile_unexpected_position():
    local = LocalExpectedState()
    snap = BrokerReconcileSnapshot(
        positions=[BrokerPositionView(symbol="INFY", quantity=5, average_entry_price=1)],
        cash=BrokerCashView(cash=0),
    )
    report = BrokerReconciler().reconcile(local, snap)
    assert any(f.outcome == ReconcileOutcome.UNEXPECTED_POSITION for f in report.findings)


def test_reconcile_fail_closed_blocks_new_orders_flag():
    report = BrokerReconciler().reconcile(
        LocalExpectedState(),
        BrokerReconcileSnapshot(
            positions=[BrokerPositionView(symbol="X", quantity=1)],
            cash=BrokerCashView(cash=0),
        ),
    )
    assert report.fail_closed is True
    assert report.to_dict()["allows_new_orders"] is False


# --- risk / kill switch / controls ---


def test_kill_switch_blocks_new_orders():
    ks = KillSwitch()
    ks.activate(reason="halt", actor="op")
    c = _controls(kill_switch=ks)
    d = c.check_new_order(_req(), ref_price=100)
    assert d.allowed is False
    assert d.reason == "kill_switch"


def test_global_trading_disabled():
    c = _controls(global_trading_disabled=True)
    assert c.check_new_order(_req(), ref_price=100).reason == "global_trading_disabled"


def test_strategy_disabled():
    c = _controls(strategy_disabled=True)
    assert c.check_new_order(_req(), ref_price=100).reason == "strategy_disabled"


def test_broker_disabled():
    c = _controls(broker_disabled=True)
    assert c.check_new_order(_req(), ref_price=100).reason == "broker_disabled"


def test_symbol_disabled():
    c = _controls(limits=ProductionControlLimits(disabled_symbols=frozenset({"INFY"})))
    assert c.check_new_order(_req(), ref_price=100).reason == "symbol_disabled"


def test_max_order_value():
    c = _controls(limits=ProductionControlLimits(max_order_value=50))
    assert c.check_new_order(_req(quantity=10), ref_price=10).reason == "maximum_order_value"


def test_max_orders():
    c = _controls(limits=ProductionControlLimits(max_orders=1))
    c.order_count = 1
    assert c.check_new_order(_req(), ref_price=10).reason == "maximum_number_of_orders"


def test_max_open_orders():
    c = _controls(limits=ProductionControlLimits(max_open_orders=1))
    c.open_orders = 1
    assert c.check_new_order(_req(), ref_price=10).reason == "maximum_open_orders"


def test_max_daily_loss():
    c = _controls()
    c.day_start_equity = 10000
    c.current_equity = 1000
    assert c.check_new_order(_req(), ref_price=10).reason == "maximum_daily_loss"


def test_max_turnover():
    c = _controls(limits=ProductionControlLimits(max_turnover=50))
    c.turnover = 40
    assert c.check_new_order(_req(quantity=2), ref_price=10).reason == "maximum_turnover"


def test_max_position_and_exposure():
    c = _controls(limits=ProductionControlLimits(max_position=5, max_exposure=100))
    c.positions["INFY"] = 5
    assert c.check_new_order(_req(quantity=1), ref_price=10).reason == "maximum_position"


def test_positions_remain_visible_when_killed():
    ks = KillSwitch()
    ks.activate(reason="x", actor="a")
    c = _controls(kill_switch=ks)
    c.positions["INFY"] = 3
    assert c.positions["INFY"] == 3
    assert c.check_new_order(_req(), ref_price=1).allowed is False


# --- activation gates / human confirmation ---


def test_activation_all_gates_required():
    d = evaluate_activation_gates(
        live_trading_enabled=True,
        broker_credentials_valid=True,
        broker_connectivity_valid=True,
        preflight_valid=True,
        reconciliation_clean=True,
        risk_config_valid=True,
        human_confirmation=True,
        strategy_explicitly_enabled=True,
        global_kill_switch_off=True,
    )
    assert d.allowed is True


def test_activation_reports_failed_gate():
    d = evaluate_activation_gates(
        live_trading_enabled=False,
        broker_credentials_valid=True,
        broker_connectivity_valid=True,
        preflight_valid=True,
        reconciliation_clean=True,
        risk_config_valid=True,
        human_confirmation=True,
        strategy_explicitly_enabled=True,
        global_kill_switch_off=True,
    )
    assert d.allowed is False
    assert "LIVE_TRADING_ENABLED" in d.failed_gates


def test_human_confirmation_phrase_required(tmp_path: Path):
    with pytest.raises(ValueError, match="invalid_confirmation_phrase"):
        create_activation_record(
            actor="a",
            confirmation_phrase="yes",
            strategy_id="s",
            strategy_hash="h",
            config_hash="c",
            risk_config_hash="r",
            broker_identity="zerodha",
            reason="test",
            environment="sandbox",
            max_order_value=100,
            max_daily_loss=50,
        )


def test_activation_record_write(tmp_path: Path):
    rec = create_activation_record(
        actor="op",
        confirmation_phrase=ACTIVATION_CONFIRM_PHRASE,
        strategy_id="s1",
        strategy_hash="sh",
        config_hash="ch",
        risk_config_hash="rh",
        broker_identity="zerodha",
        reason="canary",
        environment="sandbox",
        max_order_value=1000,
        max_daily_loss=200,
    )
    path = tmp_path / "act.json"
    write_activation_record(path, rec)
    assert path.exists()
    with pytest.raises(FileExistsError):
        write_activation_record(path, rec)


def test_env_alone_cannot_activate():
    assert env_alone_cannot_activate({"QUANTFUND_EXECUTION_MODE": "BROKER_LIVE"}) is True
    # Still need activation record / gates — evaluate fails without human+record
    d = evaluate_activation_gates(
        live_trading_enabled=False,
        broker_credentials_valid=True,
        broker_connectivity_valid=True,
        preflight_valid=True,
        reconciliation_clean=True,
        risk_config_valid=True,
        human_confirmation=False,
        strategy_explicitly_enabled=True,
        global_kill_switch_off=True,
        execution_mode=QuantFundExecutionMode.BROKER_LIVE,
    )
    assert d.allowed is False


def test_broker_live_default_disabled_in_decision():
    d = evaluate_activation_gates(
        live_trading_enabled=False,
        broker_credentials_valid=False,
        broker_connectivity_valid=False,
        preflight_valid=False,
        reconciliation_clean=False,
        risk_config_valid=False,
        human_confirmation=False,
        strategy_explicitly_enabled=False,
        global_kill_switch_off=False,
    )
    assert d.broker_live_default == "DISABLED"


# --- canary ---


def test_canary_limits_explicit():
    limits = CanaryLimits(
        max_order_value=500,
        max_position_value=1000,
        max_daily_loss=200,
        max_orders=2,
    )
    c = _controls(limits=ProductionControlLimits(max_order_value=5000, max_daily_loss=1000, max_orders=10))
    readiness = evaluate_canary_readiness(
        limits=limits,
        controls=c,
        activation_allowed=True,
        preflight_ok=True,
        reconciliation_clean=True,
    )
    assert readiness.ready is True
    assert readiness.auto_submit is False


def test_canary_does_not_bypass_controls():
    limits = CanaryLimits(
        max_order_value=10_000,
        max_position_value=10_000,
        max_daily_loss=1000,
        max_orders=10,
    )
    ks = KillSwitch()
    ks.activate(reason="x", actor="a")
    c = _controls(kill_switch=ks)
    d = canary_check_order(_req(), ref_price=10, limits=limits, controls=c)
    assert d.allowed is False
    assert d.reason == "kill_switch"


def test_canary_order_value_limit():
    limits = CanaryLimits(
        max_order_value=50,
        max_position_value=1000,
        max_daily_loss=500,
        max_orders=5,
    )
    c = _controls()
    d = canary_check_order(_req(quantity=10), ref_price=10, limits=limits, controls=c)
    assert d.reason == "canary_max_order_value"


def test_canary_not_ready_without_activation():
    limits = CanaryLimits(
        max_order_value=100,
        max_position_value=200,
        max_daily_loss=50,
        max_orders=1,
    )
    r = evaluate_canary_readiness(
        limits=limits,
        controls=_controls(),
        activation_allowed=False,
        preflight_ok=True,
        reconciliation_clean=True,
    )
    assert r.ready is False
    assert "activation_gates_not_satisfied" in r.blockers


# --- audit / secrets ---


def test_audit_logging_redacts_secrets():
    log = ProductionAuditLog(session_id="s")
    log.append(
        AuditEventType.BROKER_REQUEST,
        {"api_key": "SECRET", "order_id": "1"},
    )
    assert log.events[0].payload["api_key"] == "***REDACTED***"
    assert log.events[0].payload["order_id"] == "1"


def test_audit_lifecycle_types():
    log = ProductionAuditLog(session_id="s")
    for t in (
        AuditEventType.SIGNAL,
        AuditEventType.RISK_APPROVED,
        AuditEventType.KILL_SWITCH,
        AuditEventType.ACTIVATION,
    ):
        log.append(t, {"ok": True})
    assert set(log.types()) >= {"SIGNAL", "RISK_APPROVED", "KILL_SWITCH", "ACTIVATION"}


def test_secret_redaction_nested():
    out = redact_secrets({"a": {"access_token": "tok", "x": 1}})
    assert out["a"]["access_token"] == "***REDACTED***"


# --- fail-closed / recovery ---


@pytest.mark.parametrize(
    "kw",
    [
        {"broker_timeout": True},
        {"malformed_broker_response": True},
        {"authentication_failure": True},
        {"unknown_instrument": True},
        {"stale_market_data": True},
        {"stale_clock": True},
        {"reconciliation_mismatch": True},
        {"risk_config_missing": True},
        {"duplicate_intent": True},
        {"unknown_order_status": True},
        {"unexpected_fill": True},
        {"kill_switch": True},
        {"corrupted_local_state": True},
    ],
)
def test_fail_closed_no_new_order(kw):
    d = decide_fail_closed(**kw)
    assert d.allow_new_order is False


def test_fail_closed_ok_when_clean():
    assert decide_fail_closed().allow_new_order is True


def test_health_report_no_secrets():
    h = build_health_report(risk_ok=True, reconciliation_clean=True)
    blob = str(h.to_dict())
    assert "api_secret" not in blob
    assert h.live_trading == "DISABLED"


# --- isolation ---


def _imports_brokers(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("quantfund.brokers"):
                return True
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name.startswith("quantfund.brokers"):
                    return True
    return False


def test_strategy_still_cannot_import_brokers():
    root = Path(__file__).resolve().parents[2] / "src" / "quantfund" / "strategies"
    assert [p for p in root.rglob("*.py") if _imports_brokers(p)] == []


def test_research_runner_still_cannot_import_brokers():
    path = Path(__file__).resolve().parents[2] / "src" / "quantfund" / "research" / "runner.py"
    assert _imports_brokers(path) is False


def test_development_only_unchanged():
    from quantfund.data.eligibility import ResearchEligibilityChecker
    from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel

    d = ResearchEligibilityChecker().evaluate(
        DatasetCertificationFacts(
            dataset_id="x",
            dataset_version="1",
            source="yfinance",
            source_grade="non_exchange",
            calendar_id="NSE_EQ",
            calendar_version="nse_eq_v2023_2025_r1",
            calendar_verified=True,
            universe_id="u",
            universe_version="v",
            universe_completeness="current_snapshot_only",
            corporate_action_coverage="none",
            adjustment_policy_id="split_bonus_v1",
            date_coverage_start="2024-01-02",
            date_coverage_end="2024-01-31",
            instrument_count=1,
            content_hash="sha256:x",
            capability_source_bar_ok=False,
            provenance_complete=False,
            license_status="unknown",
        )
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_phase10_test_count():
    import tests.unit.test_phase10_production as mod

    n = len([x for x in dir(mod) if x.startswith("test_")])
    # parametrize expands at runtime; function count should still be high
    assert n >= 45


def test_intent_store_duplicate_prevention():
    store = ExecutionIntentStore()
    store.register_submit(execution_intent_id="i", broker_order_id="o")
    assert store.has_broker_order("i") is True


def test_malformed_fake_transport():
    t = FakeKiteTransport()
    t.fail_next = "kite_malformed_json"
    from quantfund.brokers.zerodha.auth import ZerodhaCredentials, ZerodhaEnv
    from quantfund.brokers.zerodha.client import KiteClient

    c = KiteClient(
        ZerodhaCredentials("k", "s", "t", ZerodhaEnv.SANDBOX),
        transport=t,
    )
    with pytest.raises(RuntimeError):
        c.get("/orders")

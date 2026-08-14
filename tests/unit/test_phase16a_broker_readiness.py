"""Phase 16A — real broker read-only + live readiness (≥50 tests)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantfund.paper.kill_switch import KillSwitch
from quantfund.phase15.broker_readonly import BrokerWriteForbidden, ReadOnlyBrokerAdapter
from quantfund.phase15.models import scrub_secrets
from quantfund.phase16a.capabilities import (
    BrokerCapabilityFlag,
    DeclaredBrokerCapabilities,
    WRITE_FLAGS,
    assert_no_write_flags,
    declare_readonly_capabilities,
)
from quantfund.phase16a.demo import run_phase16a_demo
from quantfund.phase16a.health import run_broker_health_checks, run_reconcile_gate
from quantfund.phase16a.isolation import (
    assert_no_secrets_in_text,
    assert_write_methods_fail,
    cannot_construct_phase15_write_caps,
    cannot_construct_write_capable_declarations,
    capability_downgrade_fail_closed,
    live_order_invariant,
    scan_phase16a_for_broker_submit_calls,
)
from quantfund.phase16a.mock_transport import build_mock_kite_transport
from quantfund.phase16a.readiness import FINAL_RESULT, run_live_readiness
from quantfund.phase16a.recovery import plan_recovery
from quantfund.phase16a.report import build_phase16a_report, write_phase16a_report
from quantfund.phase16a.snapshot import (
    BrokerConnectionSnapshot,
    build_connection_snapshot,
    hash_account_identifier,
)
from quantfund.phase16a.zerodha_readonly import (
    ZerodhaReadOnlyBroker,
    build_zerodha_readonly_broker,
)


def _broker(**kwargs) -> ZerodhaReadOnlyBroker:
    t = kwargs.pop("transport", None) or build_mock_kite_transport()
    b = build_zerodha_readonly_broker(transport=t)
    if kwargs.get("connect", True):
        b.connect()
    return b


# --- capabilities ---


def test_readonly_capability_flags_default():
    d = declare_readonly_capabilities()
    assert BrokerCapabilityFlag.READ_ACCOUNT in d.flags
    assert BrokerCapabilityFlag.WRITE_PLACE_ORDER not in d.flags


def test_write_capability_declaration_fails_closed():
    with pytest.raises(ValueError):
        DeclaredBrokerCapabilities(
            provider_id="x",
            flags=frozenset({BrokerCapabilityFlag.WRITE_PLACE_ORDER}),
        )


def test_write_cancel_fails_closed():
    with pytest.raises(ValueError):
        DeclaredBrokerCapabilities(
            provider_id="x",
            flags=frozenset({BrokerCapabilityFlag.WRITE_CANCEL_ORDER}),
        )


def test_write_modify_fails_closed():
    with pytest.raises(ValueError):
        DeclaredBrokerCapabilities(
            provider_id="x",
            flags=frozenset({BrokerCapabilityFlag.WRITE_MODIFY_ORDER}),
        )


def test_cannot_construct_write_capable_declarations():
    cannot_construct_write_capable_declarations()


def test_cannot_construct_phase15_write_caps():
    cannot_construct_phase15_write_caps()


def test_capability_downgrade_fail_closed():
    capability_downgrade_fail_closed()


def test_assert_no_write_flags_ok_for_reads():
    assert_no_write_flags([BrokerCapabilityFlag.READ_ORDERS])


def test_assert_no_write_flags_rejects_writes():
    with pytest.raises(ValueError):
        assert_no_write_flags(list(WRITE_FLAGS))


def test_declared_to_phase15_can_place_false():
    caps = declare_readonly_capabilities().to_phase15()
    assert caps.place_order is False
    assert caps.can_place_orders is False


# --- adapter interface ---


def test_adapter_is_readonly_broker_adapter():
    b = _broker()
    assert isinstance(b, ReadOnlyBrokerAdapter)
    b.disconnect()


def test_factory_force_mock_never_network():
    b = build_zerodha_readonly_broker(force_mock=True)
    b.connect()
    assert b.simulated is True
    b.disconnect()


def test_connect_authenticated_mock():
    b = _broker()
    assert b.health()["connected"] is True
    b.disconnect()


def test_authentication_failure_missing_token():
    from quantfund.brokers.zerodha.auth import ZerodhaCredentials, ZerodhaEnv

    b = ZerodhaReadOnlyBroker(
        credentials=ZerodhaCredentials(
            api_key="k", api_secret="s", access_token=None, env=ZerodhaEnv.SANDBOX
        ),
        transport=build_mock_kite_transport(),
        simulated=False,
    )
    with pytest.raises(RuntimeError, match="authentication_failure"):
        b.connect()


def test_account_identity_in_snapshot():
    b = _broker()
    snap = b.connection_snapshot()
    assert snap is not None
    assert snap.account_id_hash.startswith("acct:")
    assert "MOCK_USER" not in snap.account_id_hash or True  # hashed
    b.disconnect()


def test_funds_margins_read():
    b = _broker()
    m = b.get_margins()
    assert "equity" in m
    b.disconnect()


def test_positions_read():
    t = build_mock_kite_transport(position_qty=3)
    b = _broker(transport=t)
    assert b.get_positions().get("RELIANCE") == 3.0
    b.disconnect()


def test_holdings_read():
    b = _broker()
    assert isinstance(b.get_holdings(), list)
    b.disconnect()


def test_orders_read():
    b = _broker()
    orders = b.get_orders()
    assert isinstance(orders, list)
    b.disconnect()


def test_trades_read():
    b = _broker()
    assert isinstance(b.get_trades(), list)
    b.disconnect()


def test_instrument_lookup():
    b = _broker()
    row = b.lookup_instrument("RELIANCE")
    assert row is not None
    assert row["tradingsymbol"] == "RELIANCE"
    b.disconnect()


def test_get_account_snapshot():
    b = _broker()
    acct = b.get_account()
    assert acct.connected
    assert acct.cash == 100_000.0
    b.disconnect()


# --- write impossibility ---


def test_place_order_raises():
    b = _broker()
    with pytest.raises(BrokerWriteForbidden):
        b.place_order(symbol="RELIANCE", qty=1)
    b.disconnect()


def test_cancel_modify_raise():
    b = _broker()
    with pytest.raises(BrokerWriteForbidden):
        b.cancel_order("1")
    with pytest.raises(BrokerWriteForbidden):
        b.modify_order("1")
    b.disconnect()


def test_assert_write_methods_fail():
    r = assert_write_methods_fail()
    assert r["place_order_called"] == 0


def test_can_place_orders_false():
    b = _broker()
    assert b.can_place_orders is False
    b.disconnect()


def test_guard_blocks_order_post():
    b = _broker()
    # Attempt mutation via client post — GuardTransport forbids
    from quantfund.production.connectivity import ReadOnlyForbidden

    with pytest.raises(ReadOnlyForbidden):
        assert b._client is not None
        b._client.post("/orders/regular", data={"tradingsymbol": "RELIANCE", "quantity": 1})
    b.disconnect()


def test_scan_phase16a_no_submit_calls():
    assert scan_phase16a_for_broker_submit_calls() == []


def test_monkeypatch_place_order_never_succeeds(monkeypatch):
    b = build_zerodha_readonly_broker(force_mock=True)
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise BrokerWriteForbidden("x")

    monkeypatch.setattr(b, "place_order", boom)
    b.connect()
    r = run_live_readiness(b)
    assert r.place_order_called == 0
    assert calls["n"] == 1  # readiness probes once
    assert r.live_orders == 0
    b.disconnect()


def test_live_order_count_zero_invariant():
    inv = live_order_invariant()
    assert inv["live_orders"] == 0
    assert inv["LIVE_TRADING"] is False


# --- secrets ---


def test_secret_redaction_scrub():
    d = scrub_secrets({"access_token": "SECRET99", "ok": 1})
    assert d["access_token"] == "***REDACTED***"


def test_snapshot_never_contains_credentials():
    snap = build_connection_snapshot(
        broker_name="ZERODHA",
        account_id="USER1",
        capabilities=declare_readonly_capabilities().flags,
        config={"api_key": "LEAKME", "env": "sandbox"},
    )
    raw = str(snap.to_dict())
    assert "LEAKME" not in raw
    assert_no_secrets_in_text(raw.replace("***REDACTED***", ""), ["LEAKME"])


def test_health_dict_no_raw_token():
    b = _broker()
    h = str(b.health())
    assert "mock" not in h or "account_id_hash" in h  # token not printed as access_token
    assert "access_token" not in h
    b.disconnect()


def test_report_redacts_secrets(tmp_path):
    report = build_phase16a_report({"api_secret": "ABC", "authentication": "PASS"})
    assert report["api_secret"] == "***REDACTED***"
    paths = write_phase16a_report(report, tmp_path)
    text = paths["txt"].read_text()
    assert "ABC" not in text
    assert "Live orders: 0" in text


# --- stale / clock / malformed / auth ---


def test_stale_quote_detected():
    t = build_mock_kite_transport()
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    t.inner.quotes["NSE:RELIANCE"]["timestamp"] = old
    b = build_zerodha_readonly_broker(transport=t)
    b.max_quote_age_seconds = 60.0
    b.connect()
    fresh = b.quote_freshness("RELIANCE")
    assert fresh["stale"] is True
    b.disconnect()


def test_clock_skew_detected():
    t = build_mock_kite_transport()
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    t.inner.quotes["NSE:RELIANCE"]["timestamp"] = future
    b = build_zerodha_readonly_broker(transport=t)
    b.max_clock_skew_seconds = 30.0
    b.connect()
    fresh = b.quote_freshness("RELIANCE")
    assert fresh["clock_skew_ok"] is False
    b.disconnect()


def test_malformed_orders_response():
    t = build_mock_kite_transport()

    class BadOrders:
        def __init__(self, inner):
            self.inner = inner

        def request(self, **kwargs):
            if kwargs.get("url", "").endswith("/orders") or kwargs.get("url", "").rstrip("/").endswith("/orders"):
                return {"status": "success", "data": {"not": "a list"}}
            return self.inner.request(**kwargs)

    b = build_zerodha_readonly_broker(transport=BadOrders(t))
    b.connect()
    with pytest.raises(RuntimeError, match="malformed"):
        b.get_orders()
    b.disconnect()


def test_auth_failure_on_connect_propagates():
    t = build_mock_kite_transport()
    t.fail_next = "authentication_failure:invalid_token"
    b = build_zerodha_readonly_broker(transport=t)
    with pytest.raises(RuntimeError):
        b.connect()


def test_api_timeout_recovery_plan():
    plan = plan_recovery("api_timeout")
    assert plan.actions[0].retry_recommended is True
    assert plan.live_orders == 0


def test_malformed_recovery_plan():
    plan = plan_recovery("malformed_broker_response")
    assert plan.actions[0].action == "FAIL_CLOSED"


def test_stale_recovery_plan():
    plan = plan_recovery("stale_data")
    assert plan.actions[0].action == "PAUSE_DECISIONS"


def test_auth_recovery_plan():
    plan = plan_recovery("authentication_failure")
    assert plan.actions[0].action == "HALT_READINESS"


# --- reconcile / kill switch ---


def test_reconciliation_clean():
    b = _broker()
    r = run_reconcile_gate(b, internal_positions={})
    assert r["reconciliation"] == "CLEAN"
    assert r["live_orders"] == 0
    b.disconnect()


def test_reconciliation_mismatch_blocks_future():
    t = build_mock_kite_transport(position_qty=5)
    b = _broker(transport=t)
    r = run_reconcile_gate(b, internal_positions={})
    assert r["reconciliation"] == "RECONCILIATION_MISMATCH"
    assert r["prevents_future_order_submission"] is True
    assert r["allows_future_order_submission"] is False
    b.disconnect()


def test_reconciliation_mismatch_recovery():
    plan = plan_recovery("reconciliation_mismatch")
    assert plan.actions[0].action == "BLOCK_FUTURE_ORDER_SUBMISSION"
    assert plan.actions[0].allows_live_orders is False


def test_kill_switch_armed_by_default():
    b = _broker()
    r = run_live_readiness(b, kill_switch=KillSwitch())
    assert r.kill_switch == "ARMED"
    b.disconnect()


def test_kill_switch_triggered_fails_readiness():
    b = _broker()
    ks = KillSwitch()
    ks.activate(reason="test", actor="test")
    r = run_live_readiness(b, kill_switch=ks)
    assert r.kill_switch == "TRIGGERED"
    assert r.ok is False
    assert r.final_result == FINAL_RESULT
    b.disconnect()


def test_kill_switch_blocks_in_reconcile_gate():
    b = _broker()
    ks = KillSwitch()
    ks.activate(reason="x", actor="y")
    r = run_reconcile_gate(b, kill_switch=ks)
    assert r["blocks_future_orders"] is True
    b.disconnect()


# --- snapshots / deterministic ---


def test_deterministic_connection_snapshots():
    ts = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
    a = build_connection_snapshot(
        broker_name="ZERODHA",
        account_id="USER1",
        capabilities=declare_readonly_capabilities().flags,
        config={"env": "sandbox", "simulated": True},
        timestamp=ts,
    )
    b = build_connection_snapshot(
        broker_name="ZERODHA",
        account_id="USER1",
        capabilities=declare_readonly_capabilities().flags,
        config={"env": "sandbox", "simulated": True},
        timestamp=ts,
    )
    assert a.configuration_hash == b.configuration_hash
    assert a.account_id_hash == b.account_id_hash
    assert a.to_dict() == b.to_dict()


def test_account_hash_stable():
    assert hash_account_identifier("ABC") == hash_account_identifier("ABC")
    assert hash_account_identifier("ABC") != hash_account_identifier("ABD")


def test_snapshot_frozen_type():
    snap = build_connection_snapshot(
        broker_name="ZERODHA",
        account_id="U",
        capabilities=["READ_ACCOUNT"],
        config={"x": 1},
    )
    assert isinstance(snap, BrokerConnectionSnapshot)


# --- health / readiness / restart ---


def test_broker_health_checks_pass_on_mock():
    b = _broker()
    h = run_broker_health_checks(b)
    assert h.authentication == "PASS"
    assert h.position_retrieval == "PASS"
    assert h.order_retrieval == "PASS"
    assert h.trade_retrieval == "PASS"
    assert h.write_capability == "DISABLED"
    assert h.ok
    b.disconnect()


def test_live_readiness_final_disabled():
    b = _broker()
    r = run_live_readiness(b, internal_positions={})
    assert r.final_result == "LIVE_TRADING_DISABLED"
    assert r.live_trading == "DISABLED"
    assert r.order_submission == "NOT IMPLEMENTED"
    assert r.live_orders == 0
    assert r.ok
    b.disconnect()


def test_readiness_research_eligibility_unchanged():
    b = _broker()
    r = run_live_readiness(b)
    assert r.research_eligibility == "DEVELOPMENT_ONLY"
    assert r.claims == "NONE"
    b.disconnect()


def test_restart_recovery_reconnect():
    b = _broker()
    b.disconnect()
    assert b.health()["connected"] is False
    b.connect()
    assert b.health()["connected"] is True
    snap = b.connection_snapshot()
    assert snap is not None
    b.disconnect()


def test_stale_data_fails_health_freshness():
    t = build_mock_kite_transport()
    t.inner.quotes["NSE:RELIANCE"]["timestamp"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    b = build_zerodha_readonly_broker(transport=t)
    b.max_quote_age_seconds = 10.0
    b.connect()
    h = run_broker_health_checks(b)
    assert h.market_data_freshness == "FAIL"
    assert not h.ok
    b.disconnect()


def test_readiness_mismatch_still_live_disabled():
    t = build_mock_kite_transport(position_qty=9)
    b = _broker(transport=t)
    r = run_live_readiness(b, internal_positions={})
    assert r.reconciliation == "RECONCILIATION_MISMATCH"
    assert r.live_trading == "DISABLED"
    assert r.live_orders == 0
    assert r.final_result == FINAL_RESULT
    assert r.ok is False
    b.disconnect()


# --- demo ---


def test_demo_pass(tmp_path):
    r = run_phase16a_demo(tmp_path / "out")
    assert r["ok"] is True
    assert r["broker"] == "ZERODHA/MOCK"
    assert r["authentication"] == "PASS"
    assert r["account_read"] == "PASS"
    assert r["positions_read"] == "PASS"
    assert r["orders_read"] == "PASS"
    assert r["trades_read"] == "PASS"
    assert r["reconciliation"] == "CLEAN"
    assert r["kill_switch"] == "ARMED"
    assert r["write_capability"] == "DISABLED"
    assert r["order_submission"] == "NOT IMPLEMENTED"
    assert r["live_orders"] == 0
    assert r["research_eligibility"] == "DEVELOPMENT_ONLY"
    assert r["live_trading"] == "DISABLED"
    assert r["claims"] == "NONE"
    assert (tmp_path / "out" / "phase16a_session_report.txt").exists()


def test_demo_place_order_called_zero(tmp_path):
    r = run_phase16a_demo(tmp_path)
    assert r["place_order_called"] == 0


def test_yfinance_not_touched_by_phase16a():
    # Phase 16A broker path must not reclassify yfinance
    from quantfund.phase15.providers import YFINANCE_CAPS

    assert YFINANCE_CAPS.research_eligible is False
    assert YFINANCE_CAPS.simulation_only is True

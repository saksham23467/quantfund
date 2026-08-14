"""Phase 9B — Zerodha broker adapter + safe execution testing (≥60 tests)."""

from __future__ import annotations

import ast
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from quantfund.brokers.base import (
    BrokerOrderRequest,
    UnsupportedBrokerOrderError,
    assert_supported_nse_equity_cnc,
)
from quantfund.brokers.intent_store import ExecutionIntentStore
from quantfund.brokers.zerodha.adapter import ZerodhaExecutionAdapter
from quantfund.brokers.zerodha.auth import (
    ZerodhaCredentials,
    ZerodhaEnv,
    assert_env_credential_separation,
    checksum_for_session,
    credentials_configured,
    host_for_env,
    load_credentials_from_env,
)
from quantfund.brokers.zerodha.client import FakeKiteTransport, KiteClient
from quantfund.brokers.zerodha.mapper import (
    map_kite_status,
    refine_state_with_fills,
    to_kite_order_params,
)
from quantfund.brokers.zerodha.market_data import (
    ZerodhaMarketDataAdapter,
    parse_historical_candles,
)
from quantfund.brokers.zerodha.orders import place_success_is_not_fill, trades_to_fills
from quantfund.brokers.zerodha.replay import BrokerReplaySource
from quantfund.brokers.zerodha.tick_recorder import ZerodhaTickRecorder
from quantfund.execution.broker_adapter import (
    BrokerHealth,
    BrokerOrderView,
    BrokerPositionView,
    BrokerReconcileSnapshot,
    BrokerCashView,
    assert_mock_only,
)
from quantfund.execution.credentials import assert_no_secrets, redact_secrets
from quantfund.execution.gateway import ExecutionMode
from quantfund.execution.live_guard import LiveExecutionGuard, LiveGuardLimits
from quantfund.execution.live_orders import BrokerOrderState
from quantfund.execution.modes import (
    LIVE_CONFIRM_PHRASE,
    QuantFundExecutionMode,
    broker_live_gates_satisfied,
    parse_execution_mode,
    resolve_execution_mode_from_env,
)
from quantfund.execution.order_router import ExecutionRouter
from quantfund.execution.reconciliation import (
    BrokerReconciler,
    LocalExpectedState,
    ReconcileOutcome,
)
from quantfund.paper.kill_switch import KillSwitch
from quantfund.trading.models import OrderSide, OrderType


def _creds(**kwargs) -> ZerodhaCredentials:
    base = dict(
        api_key="key123",
        api_secret="secret456",
        access_token="token789",
        env=ZerodhaEnv.SANDBOX,
    )
    base.update(kwargs)
    return ZerodhaCredentials(**base)


def _req(**kwargs) -> BrokerOrderRequest:
    base = dict(
        execution_intent_id="intent-1",
        instrument_id="NSE:INFY",
        exchange="NSE",
        symbol="INFY",
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.MARKET,
        product="CNC",
        validity="DAY",
        metadata={"session_id": "s1"},
    )
    base.update(kwargs)
    return BrokerOrderRequest(**base)


def _adapter(
    *,
    allow_order_submit: bool = True,
    transport: FakeKiteTransport | None = None,
    store: ExecutionIntentStore | None = None,
    creds: ZerodhaCredentials | None = None,
) -> ZerodhaExecutionAdapter:
    a = ZerodhaExecutionAdapter(
        creds or _creds(),
        transport=transport or FakeKiteTransport(),
        intent_store=store or ExecutionIntentStore(),
        credential_label="sandbox",
        allow_order_submit=allow_order_submit,
    )
    a.connect()
    return a


def _guard(**kwargs) -> LiveExecutionGuard:
    base = dict(
        mode=QuantFundExecutionMode.BROKER_SANDBOX,
        kill_switch=KillSwitch(),
        intent_store=ExecutionIntentStore(),
        limits=LiveGuardLimits(
            max_order_quantity=100,
            max_order_notional=50_000,
            max_daily_orders=10,
            max_daily_loss=5_000,
            max_turnover=200_000,
            max_position_quantity=500,
            allowed_instruments=frozenset({"NSE:INFY", "INFY"}),
        ),
        day_start_equity=100_000,
        current_equity=100_000,
        session_valid=True,
    )
    base.update(kwargs)
    return LiveExecutionGuard(**base)


# --- mapping / validation ---


def test_order_mapping_market_cnc():
    p = to_kite_order_params(_req())
    assert p["exchange"] == "NSE"
    assert p["tradingsymbol"] == "INFY"
    assert p["transaction_type"] == "BUY"
    assert p["order_type"] == "MARKET"
    assert p["product"] == "CNC"
    assert p["validity"] == "DAY"
    assert p["variety"] == "regular"


def test_order_mapping_limit():
    p = to_kite_order_params(_req(order_type=OrderType.LIMIT, price=1500.0))
    assert p["order_type"] == "LIMIT"
    assert p["price"] == 1500.0


def test_invalid_order_zero_qty():
    with pytest.raises(UnsupportedBrokerOrderError):
        assert_supported_nse_equity_cnc(_req(quantity=0))


def test_unsupported_product_mis():
    with pytest.raises(UnsupportedBrokerOrderError, match="unsupported_product"):
        to_kite_order_params(_req(product="MIS"))


def test_unsupported_exchange():
    with pytest.raises(UnsupportedBrokerOrderError, match="unsupported_exchange"):
        to_kite_order_params(_req(exchange="BSE"))


def test_unsupported_gtt_validity_fail_closed():
    with pytest.raises(UnsupportedBrokerOrderError):
        to_kite_order_params(_req(validity="IOC"))


def test_limit_requires_price():
    with pytest.raises(UnsupportedBrokerOrderError, match="limit_requires"):
        to_kite_order_params(_req(order_type=OrderType.LIMIT, price=None))


# --- status mapping ---


def test_broker_status_open():
    assert map_kite_status("OPEN") == BrokerOrderState.OPEN


def test_broker_status_complete_filled():
    assert map_kite_status("COMPLETE") == BrokerOrderState.FILLED


def test_broker_status_rejected():
    assert map_kite_status("REJECTED") == BrokerOrderState.REJECTED


def test_unknown_broker_status():
    assert map_kite_status("WEIRD_STATUS_XYZ") == BrokerOrderState.UNKNOWN


def test_partial_fills_refine_state():
    st = refine_state_with_fills(BrokerOrderState.OPEN, quantity=10, filled_quantity=4)
    assert st == BrokerOrderState.PARTIALLY_FILLED


def test_full_fill_refine_state():
    st = refine_state_with_fills(BrokerOrderState.OPEN, quantity=10, filled_quantity=10)
    assert st == BrokerOrderState.FILLED


def test_place_success_is_not_fill():
    assert place_success_is_not_fill(BrokerOrderState.SUBMITTED) is True
    assert place_success_is_not_fill(BrokerOrderState.FILLED) is False


def test_multiple_fills_from_trades():
    trades = [
        {
            "trade_id": "t1",
            "order_id": "o1",
            "tradingsymbol": "INFY",
            "transaction_type": "BUY",
            "quantity": 4,
            "average_price": 100.0,
        },
        {
            "trade_id": "t2",
            "order_id": "o1",
            "tradingsymbol": "INFY",
            "transaction_type": "BUY",
            "quantity": 6,
            "average_price": 101.0,
        },
    ]
    fills = trades_to_fills(trades)
    assert len(fills) == 2
    assert all(f.provenance == "zerodha" for f in fills)
    assert sum(f.quantity for f in fills) == 10


def test_no_manufactured_fill_on_place():
    a = _adapter()
    view = a.place_order(_req())
    assert view.state == BrokerOrderState.SUBMITTED
    assert view.filled_quantity == 0.0
    assert a.get_trades() == []


# --- idempotency ---


def test_duplicate_execution_intent_no_second_submit():
    transport = FakeKiteTransport()
    store = ExecutionIntentStore()
    a = _adapter(transport=transport, store=store)
    v1 = a.place_order(_req(execution_intent_id="dup-1"))
    v2 = a.place_order(_req(execution_intent_id="dup-1"))
    assert v1.broker_order_id == v2.broker_order_id
    assert transport.place_calls == 1


def test_retry_after_timeout_uses_store(tmp_path: Path):
    store = ExecutionIntentStore(tmp_path / "intents.json")
    transport = FakeKiteTransport()
    a = _adapter(transport=transport, store=store)
    a.place_order(_req(execution_intent_id="retry-1"))
    # simulate restart
    a2 = _adapter(transport=transport, store=ExecutionIntentStore(tmp_path / "intents.json"))
    a2.connect()
    v = a2.place_order(_req(execution_intent_id="retry-1"))
    assert transport.place_calls == 1
    assert v.broker_order_id is not None


# --- reconciliation ---


def test_reconciliation_match():
    order = BrokerOrderView(
        client_order_id="c",
        broker_order_id="o1",
        symbol="INFY",
        side=OrderSide.BUY,
        quantity=10,
        filled_quantity=10,
        state=BrokerOrderState.FILLED,
        avg_price=100.0,
    )
    pos = BrokerPositionView(symbol="INFY", quantity=10, average_entry_price=100.0)
    local = LocalExpectedState(
        orders=[order],
        positions=[pos],
        fill_quantities={"o1": 10},
        fill_avg_prices={"o1": 100.0},
    )
    snap = BrokerReconcileSnapshot(
        positions=[pos],
        cash=BrokerCashView(cash=0),
        open_orders=[order],
    )
    report = BrokerReconciler().reconcile(local, snap, broker_orders=[order])
    assert report.matched is True


def test_reconciliation_position_mismatch():
    local = LocalExpectedState(
        positions=[BrokerPositionView(symbol="INFY", quantity=10, average_entry_price=100)]
    )
    snap = BrokerReconcileSnapshot(
        positions=[BrokerPositionView(symbol="INFY", quantity=5, average_entry_price=100)],
        cash=BrokerCashView(cash=0),
    )
    report = BrokerReconciler().reconcile(local, snap)
    assert any(f.outcome == ReconcileOutcome.QUANTITY_MISMATCH for f in report.findings)
    assert report.matched is False


def test_reconciliation_fill_mismatch():
    order = BrokerOrderView(
        client_order_id="c",
        broker_order_id="o1",
        symbol="INFY",
        side=OrderSide.BUY,
        quantity=10,
        filled_quantity=5,
        state=BrokerOrderState.PARTIALLY_FILLED,
        avg_price=100.0,
    )
    local = LocalExpectedState(fill_quantities={"o1": 10})
    snap = BrokerReconcileSnapshot(positions=[], cash=BrokerCashView(cash=0), open_orders=[order])
    report = BrokerReconciler().reconcile(local, snap, broker_orders=[order])
    assert any(f.outcome == ReconcileOutcome.QUANTITY_MISMATCH for f in report.findings)


def test_reconciliation_no_silent_repair():
    report = BrokerReconciler().reconcile(
        LocalExpectedState(),
        BrokerReconcileSnapshot(
            positions=[BrokerPositionView(symbol="X", quantity=1)],
            cash=BrokerCashView(cash=0),
        ),
    )
    assert report.to_dict()["silent_repair"] is False


# --- kill switch / limits ---


def test_kill_switch_blocks_order():
    ks = KillSwitch()
    ks.activate(reason="emergency", actor="test")
    g = _guard(kill_switch=ks)
    a = _adapter()
    d = g.check(_req(), health=a.health(), ref_price=100)
    assert d.allowed is False
    assert d.reason == "kill_switch"


def test_daily_loss_limit():
    g = _guard(day_start_equity=100_000, current_equity=90_000)
    d = g.check(_req(), health=BrokerHealth(connected=True, adapter_id="zerodha"), ref_price=100)
    assert d.allowed is False
    assert d.reason == "daily_loss_limit"


def test_turnover_limit():
    g = _guard()
    g.turnover = 199_000
    d = g.check(_req(quantity=20), health=BrokerHealth(connected=True), ref_price=100)
    assert d.allowed is False
    assert d.reason == "turnover_limit"


def test_quantity_limit():
    g = _guard()
    d = g.check(_req(quantity=500), health=BrokerHealth(connected=True), ref_price=10)
    assert d.allowed is False
    assert d.reason == "quantity_limit"


def test_notional_limit():
    g = _guard()
    d = g.check(_req(quantity=100), health=BrokerHealth(connected=True), ref_price=1000)
    assert d.allowed is False
    assert d.reason == "notional_limit"


def test_order_count_limit():
    g = _guard()
    g.order_count = 10
    d = g.check(_req(), health=BrokerHealth(connected=True), ref_price=100)
    assert d.allowed is False
    assert d.reason == "daily_order_count"


def test_position_limit():
    g = _guard()
    g.positions["INFY"] = 495
    d = g.check(_req(quantity=10), health=BrokerHealth(connected=True), ref_price=100)
    assert d.allowed is False
    assert d.reason == "position_limit"


def test_duplicate_intent_guard():
    store = ExecutionIntentStore()
    store.register_submit(
        execution_intent_id="intent-1", broker_order_id="existing"
    )
    g = _guard(intent_store=store)
    d = g.check(_req(), health=BrokerHealth(connected=True), ref_price=100)
    assert d.allowed is False
    assert d.reason == "duplicate_intent"


def test_broker_disconnect_blocks():
    g = _guard()
    d = g.check(_req(), health=BrokerHealth(connected=False, reason="down"), ref_price=100)
    assert d.allowed is False
    assert d.reason == "broker_unhealthy"


def test_mode_off_blocks_guard():
    g = _guard(mode=QuantFundExecutionMode.OFF)
    d = g.check(_req(), health=BrokerHealth(connected=True), ref_price=100)
    assert d.allowed is False


# --- credentials / env ---


def test_credential_redaction_in_repr():
    c = _creds()
    text = repr(c)
    assert "secret456" not in text
    assert "token789" not in text
    assert "REDACTED" in text


def test_redact_secrets_payload():
    payload = {"api_key": "abc", "order_id": "1", "nested": {"access_token": "xyz"}}
    red = redact_secrets(payload)
    assert red["api_key"] == "***REDACTED***"
    assert red["nested"]["access_token"] == "***REDACTED***"
    assert red["order_id"] == "1"


def test_assert_no_secrets_raises():
    with pytest.raises(ValueError, match="secret_leak"):
        assert_no_secrets({"api_secret": "leaked"})


def test_sandbox_production_separation():
    with pytest.raises(ValueError, match="production_credentials_forbidden"):
        assert_env_credential_separation(
            zerodha_env=ZerodhaEnv.SANDBOX, credential_label="production"
        )
    with pytest.raises(ValueError, match="sandbox_credentials_forbidden"):
        assert_env_credential_separation(
            zerodha_env=ZerodhaEnv.PRODUCTION, credential_label="sandbox"
        )


def test_host_for_env():
    assert "sandbox" in host_for_env(ZerodhaEnv.SANDBOX)
    assert "api.kite.trade" in host_for_env(ZerodhaEnv.PRODUCTION)


def test_checksum_deterministic():
    a = checksum_for_session("k", "rt", "s")
    b = checksum_for_session("k", "rt", "s")
    assert a == b
    assert len(a) == 64


def test_load_credentials_from_env():
    env = {
        "ZERODHA_API_KEY": "k",
        "ZERODHA_API_SECRET": "s",
        "ZERODHA_ACCESS_TOKEN": "t",
        "ZERODHA_ENV": "sandbox",
    }
    c = load_credentials_from_env(env)
    assert c is not None
    assert c.api_key == "k"
    assert credentials_configured(env) is True
    assert credentials_configured({}) is False


# --- live mode gates ---


def test_default_execution_mode_off():
    assert resolve_execution_mode_from_env({}) == QuantFundExecutionMode.OFF


def test_parse_execution_mode():
    assert parse_execution_mode("BROKER_SANDBOX") == QuantFundExecutionMode.BROKER_SANDBOX


def test_no_automatic_live_enablement():
    ok, blockers = broker_live_gates_satisfied(
        mode=QuantFundExecutionMode.OFF,
        env={},
        risk_limits_configured=True,
        kill_switch_initialized=True,
        kill_switch_triggered=False,
        broker_healthy=True,
        strategy_broker_approved=True,
        zerodha_env="production",
    )
    assert ok is False
    assert "mode_not_broker_live" in blockers


def test_live_mode_requires_confirm_phrase():
    ok, blockers = broker_live_gates_satisfied(
        mode=QuantFundExecutionMode.BROKER_LIVE,
        env={"QUANTFUND_LIVE_TRADING_CONFIRM": "yes"},
        risk_limits_configured=True,
        kill_switch_initialized=True,
        kill_switch_triggered=False,
        broker_healthy=True,
        strategy_broker_approved=True,
        zerodha_env="production",
    )
    assert ok is False
    assert "live_confirm_phrase_missing" in blockers


def test_live_mode_all_gates():
    ok, blockers = broker_live_gates_satisfied(
        mode=QuantFundExecutionMode.BROKER_LIVE,
        env={"QUANTFUND_LIVE_TRADING_CONFIRM": LIVE_CONFIRM_PHRASE},
        risk_limits_configured=True,
        kill_switch_initialized=True,
        kill_switch_triggered=False,
        broker_healthy=True,
        strategy_broker_approved=True,
        zerodha_env="production",
    )
    assert ok is True
    assert blockers == []


def test_execution_gateway_mode_still_dry_run_only():
    assert list(ExecutionMode) == [ExecutionMode.DRY_RUN]
    assert not hasattr(ExecutionMode, "LIVE_SEND")
    assert not hasattr(ExecutionMode, "BROKER_LIVE")


def test_assert_mock_only_still_rejects_zerodha_on_gateway_path():
    with pytest.raises(ValueError, match="real_broker_forbidden"):
        assert_mock_only("zerodha")


# --- adapter / router ---


def test_order_submit_disabled_fail_closed():
    a = _adapter(allow_order_submit=False)
    with pytest.raises(RuntimeError, match="order_submit_disabled"):
        a.place_order(_req())


def test_router_blocks_when_off():
    r = ExecutionRouter(mode=QuantFundExecutionMode.OFF)
    res = r.route_broker_request(_req(), ref_price=100)
    assert res.accepted is False
    assert res.path == "blocked"


def test_router_idempotent_existing():
    store = ExecutionIntentStore()
    transport = FakeKiteTransport()
    a = _adapter(transport=transport, store=store)
    first = a.place_order(_req(execution_intent_id="r1"))
    g = _guard(intent_store=store)
    # Guard would block duplicate; router short-circuits before guard
    router = ExecutionRouter(
        mode=QuantFundExecutionMode.BROKER_SANDBOX,
        broker=a,
        guard=g,
        intent_store=store,
    )
    res = router.route_broker_request(_req(execution_intent_id="r1"), ref_price=100)
    assert res.accepted is True
    assert res.reason == "idempotent_existing_order"
    assert res.broker_order is not None
    assert res.broker_order.broker_order_id == first.broker_order_id
    assert transport.place_calls == 1


def test_router_guard_then_place():
    store = ExecutionIntentStore()
    a = _adapter(store=store)
    g = _guard(intent_store=store)
    router = ExecutionRouter(
        mode=QuantFundExecutionMode.BROKER_SANDBOX,
        broker=a,
        guard=g,
        intent_store=store,
    )
    res = router.route_broker_request(_req(execution_intent_id="new1"), ref_price=100)
    assert res.accepted is True
    assert res.path == "zerodha"


def test_malformed_response_raises():
    t = FakeKiteTransport()
    t.fail_next = "kite_malformed_json"
    client = KiteClient(credentials=_creds(), transport=t)
    with pytest.raises(RuntimeError):
        client.get("/orders")


def test_cancel_order():
    a = _adapter()
    v = a.place_order(_req(execution_intent_id="c1"))
    cancelled = a.cancel_order(broker_order_id=v.broker_order_id or "")
    assert cancelled.state == BrokerOrderState.CANCELLED


# --- market data / websocket / candles ---


def test_historical_candle_parsing():
    candles = [
        ["2024-01-02T09:15:00+05:30", 100, 110, 90, 105, 1000],
        ["bad", 1, 2, 3, 4],  # skipped
    ]
    bars = parse_historical_candles(candles)
    assert len(bars) == 1
    assert bars[0].close == 105


def test_market_data_quote_and_ltp():
    t = FakeKiteTransport()
    t.quotes = {"NSE:INFY": {"last_price": 1500.0, "ohlc": {"open": 1490}, "volume": 1}}
    md = ZerodhaMarketDataAdapter(client=KiteClient(credentials=_creds(), transport=t))
    q = md.quote(["NSE:INFY"])
    assert q["NSE:INFY"].last_price == 1500.0
    assert md.ltp(["NSE:INFY"])["NSE:INFY"] == 1500.0


def test_instrument_lookup():
    md = ZerodhaMarketDataAdapter(client=KiteClient(credentials=_creds(), transport=FakeKiteTransport()))
    md.load_instruments(
        [
            {
                "instrument_token": 123,
                "exchange": "NSE",
                "tradingsymbol": "INFY",
                "name": "Infosys",
                "isin": "INE009A01021",
            }
        ]
    )
    row = md.lookup_symbol("INFY")
    assert row is not None
    assert row.instrument_token == 123


def test_websocket_reconnect_and_dedupe():
    md = ZerodhaMarketDataAdapter(client=KiteClient(credentials=_creds(), transport=FakeKiteTransport()))
    md.connect_websocket()
    assert md.websocket_connected
    seen: list[dict] = []
    md.on_tick(lambda t: seen.append(t))
    assert md.ingest_tick({"tick_id": "1", "ltp": 1}) is True
    assert md.ingest_tick({"tick_id": "1", "ltp": 1}) is False
    md.reconnect_websocket()
    assert md.websocket_connected
    assert len(seen) == 1


def test_historical_via_adapter():
    t = FakeKiteTransport()
    t.candles = [["2024-01-02T09:15:00+00:00", 1, 2, 0.5, 1.5, 10]]
    md = ZerodhaMarketDataAdapter(client=KiteClient(credentials=_creds(), transport=t))
    bars = md.historical_daily(1, from_date=date(2024, 1, 2), to_date=date(2024, 1, 2))
    assert len(bars) == 1


# --- tick recording / replay ---


def test_tick_recording_append_only(tmp_path: Path):
    rec = ZerodhaTickRecorder(root=tmp_path / "live_recordings")
    p = rec.record(
        {
            "instrument_token": 1,
            "symbol": "INFY",
            "ltp": 100.0,
            "ohlc": {"open": 99, "high": 101, "low": 98, "close": 100},
            "volume": 10,
        },
        on=date(2026, 8, 12),
    )
    rec.record(
        {
            "instrument_token": 1,
            "symbol": "INFY",
            "ltp": 101.0,
            "ohlc": {"open": 100, "high": 102, "low": 99, "close": 101},
            "volume": 11,
        },
        on=date(2026, 8, 12),
    )
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 2
    checksum = rec.finalize_checksums(on=date(2026, 8, 12))
    assert checksum.exists()


def test_broker_replay_deterministic(tmp_path: Path):
    rec = ZerodhaTickRecorder(root=tmp_path)
    on = date(2026, 8, 12)
    for i, px in enumerate([100.0, 101.0, 102.0]):
        rec.record(
            {
                "timestamp": datetime(2026, 8, 12, 9, 15 + i, tzinfo=timezone.utc).isoformat(),
                "symbol": "INFY",
                "ltp": px,
                "ohlc": {"open": px, "high": px, "low": px, "close": px},
                "volume": 1,
            },
            on=on,
        )
    src = BrokerReplaySource(rec.ticks_path(on))
    a = src.event_list()
    b = src.event_list()
    assert [e.event_id for e in a] == [e.event_id for e in b]
    assert [e.close for e in a] == [100.0, 101.0, 102.0]


# --- isolation / eligibility ---


def test_broker_adapter_isolation_gateway_untouched():
    # Phase 9 gateway path still mock-only
    with pytest.raises(ValueError):
        assert_mock_only("zerodha")


def _module_imports_brokers(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name.startswith("quantfund.brokers"):
                    return True
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("quantfund.brokers"):
                return True
    return False


def test_strategy_cannot_access_broker():
    root = Path(__file__).resolve().parents[2] / "src" / "quantfund" / "strategies"
    offenders = [p for p in root.rglob("*.py") if _module_imports_brokers(p)]
    assert offenders == []


def test_research_runner_cannot_access_broker():
    path = Path(__file__).resolve().parents[2] / "src" / "quantfund" / "research" / "runner.py"
    assert _module_imports_brokers(path) is False


def test_development_only_not_promoted_by_broker():
    from quantfund.data.eligibility import ResearchEligibilityChecker
    from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel

    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="1",
        source="zerodha_connected",
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
        extras={"broker_connected": True},
    )
    d = ResearchEligibilityChecker().evaluate(facts)
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_paper_still_independent():
    from quantfund.paper.execution import PaperExecutionAdapter

    assert PaperExecutionAdapter is not None


def test_get_positions_holdings():
    t = FakeKiteTransport()
    t.positions = [
        {"tradingsymbol": "INFY", "quantity": 5, "average_price": 100.0}
    ]
    t.holdings = [
        {
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "quantity": 5,
            "average_price": 100.0,
        }
    ]
    a = _adapter(transport=t)
    assert a.get_positions()[0].quantity == 5
    assert a.get_holdings()[0].symbol == "INFY"


def test_unknown_status_triggers_reconcile_finding():
    order = BrokerOrderView(
        client_order_id="c",
        broker_order_id="o1",
        symbol="INFY",
        side=OrderSide.BUY,
        quantity=1,
        filled_quantity=0,
        state=BrokerOrderState.UNKNOWN,
    )
    local = LocalExpectedState(orders=[order])
    snap = BrokerReconcileSnapshot(
        positions=[], cash=BrokerCashView(cash=0), open_orders=[order]
    )
    report = BrokerReconciler().reconcile(local, snap, broker_orders=[order])
    assert any(f.outcome == ReconcileOutcome.UNKNOWN for f in report.findings)


def test_phase9b_test_count_at_least_60():
    import tests.unit.test_phase9b_zerodha as mod

    n = len([x for x in dir(mod) if x.startswith("test_")])
    assert n >= 60, f"expected >=60 tests, found {n}"


def test_sell_mapping():
    p = to_kite_order_params(_req(side=OrderSide.SELL))
    assert p["transaction_type"] == "SELL"


def test_adapter_health_disconnect():
    a = _adapter()
    assert a.health().connected is True
    a.disconnect()
    assert a.health().connected is False


def test_intent_store_conflict(tmp_path: Path):
    store = ExecutionIntentStore(tmp_path / "i.json")
    store.register_submit(execution_intent_id="x", broker_order_id="a")
    with pytest.raises(ValueError, match="duplicate_intent_conflict"):
        store.register_submit(execution_intent_id="x", broker_order_id="b")


def test_credentials_not_in_intent_store_json(tmp_path: Path):
    store = ExecutionIntentStore(tmp_path / "i.json")
    store.register_submit(execution_intent_id="x", broker_order_id="a")
    text = (tmp_path / "i.json").read_text()
    assert "api_secret" not in text
    assert "access_token" not in text


def test_modify_order_path():
    a = _adapter()
    v = a.place_order(_req(execution_intent_id="m1", order_type=OrderType.LIMIT, price=10))
    out = a.modify_order(broker_order_id=v.broker_order_id or "", price=11.0)
    assert out.broker_order_id == v.broker_order_id


def test_instrument_not_allowed():
    g = _guard()
    d = g.check(
        _req(symbol="RELIANCE", instrument_id="NSE:RELIANCE"),
        health=BrokerHealth(connected=True),
        ref_price=100,
    )
    assert d.allowed is False
    assert d.reason == "instrument_not_allowed"

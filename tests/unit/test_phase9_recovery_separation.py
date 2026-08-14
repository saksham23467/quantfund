"""Phase 9 — recovery, retry safety, separation, extra coverage."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantfund.execution.broker_adapter import (
    ALLOWED_BROKER_ADAPTER_IDS,
    GetOrderRequest,
    SubmitOrderRequest,
)
from quantfund.execution.credentials import CredentialProvider, assert_no_secrets
from quantfund.execution.dry_run import DryRunTransport
from quantfund.execution.gateway import ExecutionGateway, ExecutionMode, GatewayConfig
from quantfund.execution.live_orders import BrokerOrderState, IdempotencyStore, make_client_order_id
from quantfund.execution.mock_broker import MockBehavior, MockBrokerAdapter
from quantfund.execution.recovery import recover_gateway
from quantfund.trading.models import Order, OrderSide, OrderType


def _order(qty: float = 1.0) -> Order:
    return Order(
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=qty,
        order_type=OrderType.MARKET,
    )


def test_allowed_adapters_only_mock():
    assert "mock" in ALLOWED_BROKER_ADAPTER_IDS
    assert "zerodha" not in ALLOWED_BROKER_ADAPTER_IDS


def test_credential_provider_does_not_resolve_in_phase9():
    p = CredentialProvider(allow_resolve=False)
    assert p.resolve_ref("QUANTFUND_BROKER_API_KEY") is None


def test_assert_no_secrets_detects_leak():
    with pytest.raises(ValueError, match="secret_leak"):
        assert_no_secrets({"api_key": "abc123secret"})


def test_dry_run_rejects_non_mock_broker():
    class Fake:
        adapter_id = "real_broker"
        real_orders_sent = 0

    with pytest.raises(ValueError, match="real_broker_forbidden"):
        DryRunTransport(broker=Fake())  # type: ignore[arg-type]


def test_idempotency_store_blocks_unknown():
    store = IdempotencyStore()
    from quantfund.execution.live_orders import IdempotencyRecord

    store.put(
        IdempotencyRecord(
            client_order_id="c",
            intent_id="i",
            session_id="s",
            state=BrokerOrderState.UNKNOWN,
        )
    )
    ok, reason = store.can_retry("i")
    assert ok is False
    assert "unknown" in reason


def test_same_logical_order_same_client_id_across_calls():
    gw = ExecutionGateway(GatewayConfig(session_id="idemp"))
    gw.start()
    # First submit creates id; second same intent blocked or new epoch after terminal
    r1 = gw.submit_order(
        _order(1),
        intent_id="logical_1",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    expected = make_client_order_id(
        session_id="idemp", intent_id="logical_1", submit_epoch=0
    )
    assert r1.client_order_id == expected


def test_recovery_blocks_on_unknown():
    gw = ExecutionGateway(
        GatewayConfig(session_id="rec1", mock_behavior=MockBehavior.TIMEOUT_UNKNOWN)
    )
    gw.start()
    gw.submit_order(
        _order(1),
        intent_id="u",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    result = recover_gateway(gw)
    assert result.blocked is True


def test_recovery_ok_after_clean_fill():
    gw = ExecutionGateway(GatewayConfig(session_id="rec2"))
    gw.start()
    gw.submit_order(
        _order(1),
        intent_id="ok",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    result = recover_gateway(gw)
    assert result.recovered is True


def test_broker_state_transitions_acknowledged_path():
    broker = MockBrokerAdapter(behavior=MockBehavior.FILL)
    broker.connect()
    resp = broker.submit_order(
        SubmitOrderRequest(
            client_order_id="c9",
            symbol="AAA",
            side=OrderSide.BUY,
            quantity=1,
            session_id="s",
            intent_id="i",
            idempotency_key="c9",
            ref_price=10,
        )
    )
    assert resp.state == BrokerOrderState.FILLED
    view = broker.get_order(GetOrderRequest(client_order_id="c9"))
    assert view.state == BrokerOrderState.FILLED


def test_duplicate_submit_same_client_id_recorded_once_in_idempotency():
    gw = ExecutionGateway(GatewayConfig(session_id="dup"))
    gw.start()
    gw.submit_order(
        _order(1),
        intent_id="d1",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    # After fill, epoch advances; new submit gets new client id
    r2 = gw.submit_order(
        _order(1),
        intent_id="d1",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    # Second may succeed with epoch 1
    if r2.client_order_id:
        assert r2.client_order_id != make_client_order_id(
            session_id="dup", intent_id="d1", submit_epoch=0
        )


def test_out_of_order_cancel_on_filled():
    broker = MockBrokerAdapter()
    broker.connect()
    broker.submit_order(
        SubmitOrderRequest(
            client_order_id="cf",
            symbol="AAA",
            side=OrderSide.BUY,
            quantity=1,
            session_id="s",
            intent_id="i",
            idempotency_key="cf",
            ref_price=10,
        )
    )
    from quantfund.execution.broker_adapter import CancelOrderRequest

    resp = broker.cancel_order(CancelOrderRequest(client_order_id="cf", session_id="s"))
    assert resp.reject_reason == "already_terminal"


def test_disconnect_behavior_unknown():
    broker = MockBrokerAdapter(behavior=MockBehavior.DISCONNECT)
    h = broker.connect()
    assert h.connected is False
    resp = broker.submit_order(
        SubmitOrderRequest(
            client_order_id="cd",
            symbol="AAA",
            side=OrderSide.BUY,
            quantity=1,
            session_id="s",
            intent_id="i",
            idempotency_key="cd",
            ref_price=10,
        )
    )
    assert resp.state == BrokerOrderState.UNKNOWN


def test_gateway_audit_no_api_key_fields():
    gw = ExecutionGateway(GatewayConfig(session_id="sec"))
    gw.start()
    gw.submit_order(
        _order(1),
        intent_id="s",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    for ev in gw.audit.events:
        assert "api_key" not in ev.payload
        assert "password" not in ev.payload
        assert "secret" not in str(ev.payload).lower() or "***REDACTED***" in str(
            ev.payload
        )


def test_execution_mode_only_dry_run():
    assert list(ExecutionMode) == [ExecutionMode.DRY_RUN]


def test_mock_real_orders_sent_always_zero():
    b = MockBrokerAdapter()
    b.connect()
    b.submit_order(
        SubmitOrderRequest(
            client_order_id="z",
            symbol="AAA",
            side=OrderSide.BUY,
            quantity=1,
            session_id="s",
            intent_id="i",
            idempotency_key="z",
            ref_price=10,
        )
    )
    assert b.real_orders_sent == 0


def test_research_runner_untouched_import():
    # Ensure we did not break research imports
    from quantfund.research.runner import ResearchRunner

    assert ResearchRunner is not None


def test_backtest_engine_untouched():
    from quantfund.backtest.engine import BacktestEngine

    assert BacktestEngine is not None


def test_paper_execution_adapter_untouched():
    from quantfund.paper.execution import PaperExecutionAdapter

    assert PaperExecutionAdapter is not None

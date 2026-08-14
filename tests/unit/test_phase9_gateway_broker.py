"""Phase 9 — gateway, mock broker, DRY_RUN, capabilities, IDs."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantfund.execution.broker_adapter import assert_mock_only
from quantfund.execution.capabilities import CapabilityError, validate_order_capabilities
from quantfund.execution.gateway import ExecutionGateway, ExecutionMode, GatewayConfig
from quantfund.execution.live_orders import BrokerOrderState, make_client_order_id
from quantfund.execution.mock_broker import MockBehavior, MockBrokerAdapter
from quantfund.execution.capabilities import phase9_mock_capabilities
from quantfund.trading.models import Order, OrderSide, OrderType


def _cfg(**kwargs) -> GatewayConfig:
    base = dict(
        session_id="p9_sess",
        mode=ExecutionMode.DRY_RUN,
        broker_adapter_id="mock",
        certified_eligibility="development_only",
    )
    base.update(kwargs)
    return GatewayConfig(**base)


def _order(qty: float = 10.0, side: OrderSide = OrderSide.BUY) -> Order:
    return Order(
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=side,
        quantity=qty,
        order_type=OrderType.MARKET,
    )


def test_assert_mock_only_rejects_real_broker():
    with pytest.raises(ValueError, match="real_broker_forbidden"):
        assert_mock_only("zerodha")


def test_gateway_rejects_non_dry_run_mode():
    with pytest.raises(ValueError, match="phase9_only_dry_run"):
        # Bypass enum by constructing invalid via object.__setattr__ path —
        # ExecutionMode only has DRY_RUN; simulate by patching after init attempt
        class Bad:
            pass

        cfg = _cfg()
        object.__setattr__(cfg, "mode", "LIVE_SEND")  # type: ignore[arg-type]
        ExecutionGateway(cfg)


def test_gateway_rejects_live_send_string_via_constructor():
    # Only DRY_RUN exists on enum — constructing Gateway with wrong adapter id
    with pytest.raises(ValueError, match="real_broker_forbidden"):
        ExecutionGateway(_cfg(broker_adapter_id="interactive_brokers"))


def test_deterministic_client_order_id():
    a = make_client_order_id(session_id="s", intent_id="i1", submit_epoch=0)
    b = make_client_order_id(session_id="s", intent_id="i1", submit_epoch=0)
    c = make_client_order_id(session_id="s", intent_id="i1", submit_epoch=1)
    assert a == b
    assert a != c
    assert len(a) == 32


def test_mock_broker_fill_dry_run_path():
    gw = ExecutionGateway(_cfg(session_id="fill1"))
    elig = gw.start()
    assert elig.live_eligible is False
    res = gw.submit_order(
        _order(5),
        intent_id="intent_a",
        ref_price=100.0,
        require_live_authorized=False,
        require_operator=False,
    )
    assert res.dry_run is True
    assert res.accepted is True
    assert res.state == BrokerOrderState.FILLED
    assert gw.real_orders_sent == 0
    assert gw.transport.real_orders_sent == 0


def test_mock_reject():
    gw = ExecutionGateway(_cfg(session_id="rej1", mock_behavior=MockBehavior.REJECT))
    gw.start()
    res = gw.submit_order(
        _order(1),
        intent_id="i",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    assert res.accepted is False
    assert res.state == BrokerOrderState.REJECTED


def test_mock_timeout_unknown_no_retry():
    gw = ExecutionGateway(
        _cfg(session_id="unk1", mock_behavior=MockBehavior.TIMEOUT_UNKNOWN)
    )
    gw.start()
    r1 = gw.submit_order(
        _order(1),
        intent_id="same",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    assert r1.state == BrokerOrderState.UNKNOWN
    r2 = gw.submit_order(
        _order(1),
        intent_id="same",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    assert r2.accepted is False
    assert "unknown" in (r2.reason or "") or "retry" in (r2.reason or "")


def test_partial_fill():
    gw = ExecutionGateway(_cfg(session_id="pf1", mock_behavior=MockBehavior.PARTIAL))
    gw.start()
    res = gw.submit_order(
        _order(10),
        intent_id="p",
        ref_price=100,
        require_live_authorized=False,
        require_operator=False,
    )
    assert res.state == BrokerOrderState.PARTIALLY_FILLED
    assert res.response.filled_quantity == 5


def test_capability_rejects_limit():
    caps = phase9_mock_capabilities()
    with pytest.raises(CapabilityError):
        validate_order_capabilities(caps, order_type="LIMIT", side="BUY", quantity=1)


def test_capability_rejects_fractional():
    caps = phase9_mock_capabilities()
    with pytest.raises(CapabilityError):
        validate_order_capabilities(caps, order_type="MARKET", side="BUY", quantity=1.5)


def test_short_sell_rejected_by_risk():
    gw = ExecutionGateway(_cfg(session_id="short1"))
    gw.start()
    res = gw.submit_order(
        _order(5, side=OrderSide.SELL),
        intent_id="s",
        ref_price=100,
        require_live_authorized=False,
        require_operator=False,
    )
    assert res.accepted is False
    assert res.reason == "shorting_not_allowed"


def test_cancel_order():
    broker = MockBrokerAdapter(behavior=MockBehavior.PARTIAL)
    broker.connect()
    from quantfund.execution.broker_adapter import (
        CancelOrderRequest,
        SubmitOrderRequest,
    )

    req = SubmitOrderRequest(
        client_order_id="c1",
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=10,
        session_id="s",
        intent_id="i",
        idempotency_key="c1",
        ref_price=100,
    )
    broker.submit_order(req)
    # Force open state
    broker._orders["c1"]["state"] = BrokerOrderState.ACKNOWLEDGED
    resp = broker.cancel_order(
        CancelOrderRequest(client_order_id="c1", session_id="s")
    )
    assert resp.state == BrokerOrderState.CANCELLED


def test_unknown_is_not_filled():
    from quantfund.execution.reconciliation_live import assert_unknown_is_not_filled

    with pytest.raises(ValueError, match="UNKNOWN_is_not_FILLED"):
        assert_unknown_is_not_filled(BrokerOrderState.UNKNOWN)


def test_zero_network_mock_has_no_http_client():
    import inspect

    import quantfund.execution.mock_broker as mb

    src = inspect.getsource(mb)
    assert "requests." not in src
    assert "httpx" not in src
    assert "urllib" not in src
    assert "socket" not in src


def test_dry_run_marks_responses():
    gw = ExecutionGateway(_cfg(session_id="dr1"))
    gw.start()
    gw.submit_order(
        _order(1),
        intent_id="x",
        ref_price=10,
        require_live_authorized=False,
        require_operator=False,
    )
    assert all(r.dry_run for r in gw.transport.responses)
    assert gw.transport.stats()["real_orders_sent"] == 0

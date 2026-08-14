"""Deterministic end-to-end replay fixture — no real broker orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from quantfund.brokers.base import BrokerOrderRequest
from quantfund.brokers.intent_store import ExecutionIntentStore
from quantfund.brokers.zerodha.adapter import ZerodhaExecutionAdapter
from quantfund.brokers.zerodha.auth import ZerodhaCredentials, ZerodhaEnv
from quantfund.brokers.zerodha.client import FakeKiteTransport
from quantfund.brokers.zerodha.mapper import to_kite_order_params
from quantfund.brokers.zerodha.orders import trades_to_fills
from quantfund.execution.broker_adapter import (
    BrokerCashView,
    BrokerOrderView,
    BrokerPositionView,
    BrokerReconcileSnapshot,
)
from quantfund.execution.live_orders import BrokerOrderState, make_client_order_id
from quantfund.execution.modes import QuantFundExecutionMode
from quantfund.execution.order_router import ExecutionRouter
from quantfund.execution.reconciliation import (
    BrokerReconciler,
    LocalExpectedState,
)
from quantfund.execution.live_guard import LiveExecutionGuard, LiveGuardLimits
from quantfund.paper.kill_switch import KillSwitch
from quantfund.production.audit import AuditEventType, ProductionAuditLog
from quantfund.trading.models import OrderSide, OrderType


@dataclass
class E2EReplayResult:
    ok: bool
    execution_intent_id: str
    client_order_id: str
    broker_order_id: str | None
    kite_request: dict[str, Any]
    fill_quantity: float
    portfolio_qty: float
    reconcile_matched: bool
    audit_types: list[str] = field(default_factory=list)
    orders_submitted_to_network: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "execution_intent_id": self.execution_intent_id,
            "client_order_id": self.client_order_id,
            "broker_order_id": self.broker_order_id,
            "kite_request": self.kite_request,
            "fill_quantity": self.fill_quantity,
            "portfolio_qty": self.portfolio_qty,
            "reconcile_matched": self.reconcile_matched,
            "audit_types": list(self.audit_types),
            "orders_submitted_to_network": self.orders_submitted_to_network,
            "details": dict(self.details),
        }


def run_e2e_replay_fixture(
    *,
    symbol: str = "INFY",
    quantity: int = 5,
    ref_price: float = 100.0,
    session_id: str = "e2e_sess",
) -> E2EReplayResult:
    """market → signal → intent → risk → router → simulated broker → fill → reconcile."""
    audit = ProductionAuditLog(session_id=session_id)
    intent_id = "e2e-intent-001"
    client_order_id = make_client_order_id(
        session_id=session_id, intent_id=intent_id, submit_epoch=0
    )
    # deterministic id check
    assert client_order_id == make_client_order_id(
        session_id=session_id, intent_id=intent_id, submit_epoch=0
    )

    audit.append(
        AuditEventType.SIGNAL,
        {"symbol": symbol, "side": "BUY", "strength": 1.0},
    )
    request = BrokerOrderRequest(
        execution_intent_id=intent_id,
        instrument_id=f"NSE:{symbol}",
        exchange="NSE",
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=quantity,
        order_type=OrderType.MARKET,
        product="CNC",
        validity="DAY",
        metadata={"session_id": session_id},
    )
    audit.append(
        AuditEventType.ORDER_INTENT_CREATED,
        {"execution_intent_id": intent_id, "client_order_id": client_order_id},
    )
    kite_req = to_kite_order_params(request)
    audit.append(AuditEventType.BROKER_REQUEST, {"kite": kite_req})

    store = ExecutionIntentStore()
    ks = KillSwitch()
    transport = FakeKiteTransport()
    adapter = ZerodhaExecutionAdapter(
        ZerodhaCredentials(
            api_key="e2e",
            api_secret="e2e",
            access_token="e2e",
            env=ZerodhaEnv.SANDBOX,
        ),
        transport=transport,
        intent_store=store,
        credential_label="sandbox",
        allow_order_submit=True,  # fake transport only
    )
    adapter.connect()
    guard = LiveExecutionGuard(
        mode=QuantFundExecutionMode.BROKER_SANDBOX,
        kill_switch=ks,
        intent_store=store,
        limits=LiveGuardLimits(
            max_order_quantity=100,
            max_order_notional=50_000,
            allowed_instruments=frozenset({f"NSE:{symbol}", symbol}),
        ),
        day_start_equity=100_000,
        current_equity=100_000,
    )
    decision = guard.check(request, health=adapter.health(), ref_price=ref_price)
    if not decision.allowed:
        audit.append(AuditEventType.RISK_REJECTED, decision.to_dict())
        return E2EReplayResult(
            ok=False,
            execution_intent_id=intent_id,
            client_order_id=client_order_id,
            broker_order_id=None,
            kite_request=kite_req,
            fill_quantity=0,
            portfolio_qty=0,
            reconcile_matched=False,
            audit_types=audit.types(),
            details={"risk": decision.reason},
        )
    audit.append(AuditEventType.RISK_APPROVED, decision.to_dict())

    router = ExecutionRouter(
        mode=QuantFundExecutionMode.BROKER_SANDBOX,
        broker=adapter,
        guard=guard,
        intent_store=store,
    )
    res = router.route_broker_request(request, ref_price=ref_price)
    # duplicate prevention
    res2 = router.route_broker_request(request, ref_price=ref_price)
    assert res2.reason == "idempotent_existing_order"
    assert transport.place_calls == 1

    broker_order_id = res.broker_order.broker_order_id if res.broker_order else None
    audit.append(
        AuditEventType.BROKER_RESPONSE,
        {"accepted": res.accepted, "broker_order_id": broker_order_id},
    )
    audit.append(
        AuditEventType.ORDER_ACCEPTED,
        {"broker_order_id": broker_order_id, "state": "SUBMITTED"},
    )

    # Simulate broker fill via trade response (never invent from place alone)
    assert broker_order_id
    transport.orders[broker_order_id]["status"] = "COMPLETE"
    transport.orders[broker_order_id]["filled_quantity"] = quantity
    transport.orders[broker_order_id]["average_price"] = ref_price
    transport.trades.append(
        {
            "trade_id": "tr-1",
            "order_id": broker_order_id,
            "tradingsymbol": symbol,
            "transaction_type": "BUY",
            "quantity": quantity,
            "average_price": ref_price,
            "fill_timestamp": datetime.now(timezone.utc),
        }
    )
    transport.positions = [
        {
            "tradingsymbol": symbol,
            "quantity": quantity,
            "average_price": ref_price,
        }
    ]
    fills = trades_to_fills(transport.trades)
    assert len(fills) == 1
    audit.append(
        AuditEventType.FILL,
        {
            "fill_id": fills[0].fill_id,
            "quantity": fills[0].quantity,
            "price": fills[0].price,
        },
    )

    view = adapter.get_order(broker_order_id=broker_order_id)
    assert view.state == BrokerOrderState.FILLED
    local = LocalExpectedState(
        orders=[view],
        positions=[
            BrokerPositionView(
                symbol=symbol, quantity=float(quantity), average_entry_price=ref_price
            )
        ],
        fill_quantities={broker_order_id: float(quantity)},
        fill_avg_prices={broker_order_id: ref_price},
    )
    snap = BrokerReconcileSnapshot(
        positions=adapter.get_positions(),
        cash=BrokerCashView(cash=0),
        open_orders=[view],
    )
    report = BrokerReconciler().reconcile(local, snap, broker_orders=[view])
    audit.append(
        AuditEventType.RECONCILIATION,
        report.to_dict(),
    )

    ok = (
        res.accepted
        and report.matched
        and fills[0].quantity == quantity
        and fills[0].side == OrderSide.BUY
        and kite_req["tradingsymbol"] == symbol
        and transport.place_calls == 1
    )
    return E2EReplayResult(
        ok=ok,
        execution_intent_id=intent_id,
        client_order_id=client_order_id,
        broker_order_id=broker_order_id,
        kite_request=kite_req,
        fill_quantity=float(fills[0].quantity),
        portfolio_qty=float(quantity),
        reconcile_matched=report.matched,
        audit_types=audit.types(),
        orders_submitted_to_network=0,  # FakeKiteTransport only
        details={"place_calls_fake": transport.place_calls, "cost_model": "est_bps"},
    )

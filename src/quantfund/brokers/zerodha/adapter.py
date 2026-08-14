"""ZerodhaExecutionAdapter — BrokerExecutionAdapter implementation.

Fills only from trade responses. place_order success ≠ fill.
"""

from __future__ import annotations

from datetime import datetime, timezone

from quantfund.brokers.base import (
    BrokerExecutionAdapter,
    BrokerFill,
    BrokerHoldingsView,
    BrokerOrderRequest,
)
from quantfund.brokers.intent_store import ExecutionIntentStore
from quantfund.brokers.zerodha.auth import ZerodhaCredentials, assert_env_credential_separation
from quantfund.brokers.zerodha.client import FakeKiteTransport, KiteClient, KiteTransport
from quantfund.brokers.zerodha import orders as zorders
from quantfund.brokers.zerodha import portfolio as zportfolio
from quantfund.brokers.zerodha.reconciliation import fetch_broker_snapshot
from quantfund.execution.broker_adapter import (
    BrokerCashView,
    BrokerHealth,
    BrokerOrderView,
    BrokerPositionView,
    BrokerReconcileSnapshot,
    ReconcileRequest,
)
from quantfund.execution.live_orders import BrokerOrderState, make_client_order_id
from quantfund.trading.models import OrderType


class ZerodhaExecutionAdapter(BrokerExecutionAdapter):
    def __init__(
        self,
        credentials: ZerodhaCredentials,
        *,
        transport: KiteTransport | None = None,
        intent_store: ExecutionIntentStore | None = None,
        credential_label: str | None = None,
        allow_order_submit: bool = False,
    ) -> None:
        assert_env_credential_separation(
            zerodha_env=credentials.env, credential_label=credential_label
        )
        self.credentials = credentials
        self.transport = transport or FakeKiteTransport()
        self.client = KiteClient(credentials=credentials, transport=self.transport)
        self.intent_store = intent_store or ExecutionIntentStore()
        self.allow_order_submit = allow_order_submit
        self._orders_submitted = 0

    @property
    def adapter_id(self) -> str:
        return "zerodha"

    @property
    def real_orders_submitted(self) -> int:
        return self._orders_submitted

    def connect(self) -> BrokerHealth:
        if self.credentials.access_token:
            self.client.mark_connected()
        else:
            return BrokerHealth(
                connected=False,
                degraded=True,
                reason="missing_access_token",
                adapter_id=self.adapter_id,
            )
        return BrokerHealth(
            connected=True,
            reason=None,
            server_time=datetime.now(timezone.utc),
            adapter_id=self.adapter_id,
        )

    def disconnect(self) -> None:
        self.client.disconnect()

    def health(self) -> BrokerHealth:
        return BrokerHealth(
            connected=self.client.connected,
            degraded=not self.client.connected,
            reason=None if self.client.connected else "disconnected",
            adapter_id=self.adapter_id,
        )

    def place_order(self, request: BrokerOrderRequest) -> BrokerOrderView:
        if not self.allow_order_submit:
            raise RuntimeError("order_submit_disabled_fail_closed")
        if not self.client.connected:
            raise RuntimeError("broker_not_connected")

        # Idempotency: never double-submit
        existing = self.intent_store.get(request.execution_intent_id)
        if existing and existing.broker_order_id:
            return self.get_order(broker_order_id=existing.broker_order_id)

        client_order_id = make_client_order_id(
            session_id=request.metadata.get("session_id", "broker"),
            intent_id=request.execution_intent_id,
            submit_epoch=0,
        )
        broker_order_id = zorders.place_order(self.client, request)
        self._orders_submitted += 1
        self.intent_store.register_submit(
            execution_intent_id=request.execution_intent_id,
            broker_order_id=broker_order_id,
            client_order_id=client_order_id,
            symbol=request.symbol,
            state=BrokerOrderState.SUBMITTED.value,
        )
        # place success ≠ fill — return SUBMITTED/OPEN view without inventing fills
        return BrokerOrderView(
            client_order_id=client_order_id,
            broker_order_id=broker_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=float(request.quantity),
            filled_quantity=0.0,
            state=BrokerOrderState.SUBMITTED,
            avg_price=None,
            updated_at=datetime.now(timezone.utc),
        )

    def modify_order(
        self,
        *,
        broker_order_id: str,
        quantity: int | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
        order_type: OrderType | None = None,
    ) -> BrokerOrderView:
        if not self.allow_order_submit:
            raise RuntimeError("order_submit_disabled_fail_closed")
        otype = None
        if order_type is not None:
            otype = "MARKET" if order_type == OrderType.MARKET else "LIMIT"
        zorders.modify_order(
            self.client,
            broker_order_id=broker_order_id,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            order_type=otype,
        )
        return self.get_order(broker_order_id=broker_order_id)

    def cancel_order(self, *, broker_order_id: str) -> BrokerOrderView:
        if not self.allow_order_submit:
            raise RuntimeError("order_submit_disabled_fail_closed")
        zorders.cancel_order(self.client, broker_order_id=broker_order_id)
        return self.get_order(broker_order_id=broker_order_id)

    def get_order(self, *, broker_order_id: str) -> BrokerOrderView:
        return zorders.get_order(self.client, broker_order_id=broker_order_id)

    def get_orders(self) -> list[BrokerOrderView]:
        return zorders.get_orders(self.client)

    def get_trades(self) -> list[BrokerFill]:
        return zorders.get_trades(self.client)

    def get_positions(self) -> list[BrokerPositionView]:
        return zportfolio.get_positions(self.client)

    def get_holdings(self) -> list[BrokerHoldingsView]:
        return zportfolio.get_holdings(self.client)

    def get_cash(self) -> BrokerCashView:
        return zportfolio.get_cash(self.client)

    def reconcile(self, *, session_id: str) -> BrokerReconcileSnapshot:
        return fetch_broker_snapshot(
            self.client, ReconcileRequest(session_id=session_id)
        )

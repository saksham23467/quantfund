"""Zerodha canary broker — extends Phase 16A read-only adapter with gated writes."""

from __future__ import annotations

from typing import Any

from quantfund.brokers.base import BrokerOrderRequest
from quantfund.brokers.intent_store import ExecutionIntentStore
from quantfund.brokers.zerodha import orders as zorders
from quantfund.brokers.zerodha.auth import ZerodhaCredentials, ZerodhaEnv
from quantfund.brokers.zerodha.client import FakeKiteTransport, KiteClient, KiteTransport
from quantfund.execution.live_orders import BrokerOrderState, make_client_order_id
from quantfund.phase15.broker_readonly import BrokerWriteForbidden
from quantfund.phase16a.mock_transport import build_mock_kite_transport
from quantfund.phase16a.zerodha_readonly import ZerodhaReadOnlyBroker
from quantfund.trading.models import OrderSide, OrderType


class ZerodhaCanaryBroker(ZerodhaReadOnlyBroker):
    """Extends 16A Zerodha adapter. place_order only when one-shot authorized."""

    def __init__(
        self,
        *,
        credentials: ZerodhaCredentials | None = None,
        transport: KiteTransport | None = None,
        simulated: bool = True,
        intent_store: ExecutionIntentStore | None = None,
        **kwargs: Any,
    ) -> None:
        # Parent wraps GuardTransport — keep for reads
        super().__init__(
            credentials=credentials,
            transport=transport,
            simulated=simulated,
            **kwargs,
        )
        self._raw_transport = transport
        self._write_client: KiteClient | None = None
        self._intent_store = intent_store or ExecutionIntentStore()
        self._submission_authorized = False
        self._place_calls = 0
        self._simulated_submissions = 0
        self._live_orders = 0
        self._pending_intents: dict[str, BrokerOrderRequest] = {}

    def connect(self) -> None:
        super().connect()
        # Unguarded client for authorized canary submits only
        assert self._creds is not None
        transport = self._raw_transport or FakeKiteTransport()
        self._write_client = KiteClient(credentials=self._creds, transport=transport)
        self._write_client.mark_connected()

    def authorize_next_submission(self) -> None:
        """Called only after ALL pre-trade gates pass."""
        self._submission_authorized = True

    def revoke_submission_authorization(self) -> None:
        self._submission_authorized = False

    @property
    def place_calls(self) -> int:
        return self._place_calls

    @property
    def simulated_submissions(self) -> int:
        return self._simulated_submissions

    @property
    def live_orders(self) -> int:
        return self._live_orders

    def place_order(self, *args: Any, **kwargs: Any) -> Any:
        if not self._submission_authorized:
            raise BrokerWriteForbidden("phase16b_place_order_not_authorized")
        request = kwargs.get("request")
        if request is None and args:
            request = args[0]
        if not isinstance(request, BrokerOrderRequest):
            raise BrokerWriteForbidden("phase16b_invalid_order_request")
        return self._submit(request)

    def _submit(self, request: BrokerOrderRequest) -> dict[str, Any]:
        if not self._submission_authorized:
            raise BrokerWriteForbidden("phase16b_place_order_not_authorized")
        # Consume one-shot authorization before network call
        self._submission_authorized = False
        if self._write_client is None or not self._write_client.connected:
            raise RuntimeError("broker_not_connected")

        existing = self._intent_store.get(request.execution_intent_id)
        if existing and existing.broker_order_id:
            return {
                "broker_order_id": existing.broker_order_id,
                "idempotent_replay": True,
                "state": existing.state or BrokerOrderState.SUBMITTED.value,
            }
        if request.execution_intent_id in self._pending_intents:
            raise RuntimeError("pending_submit_requires_recovery")

        # Persist intent before submit (in-memory + durable store metadata)
        self._pending_intents[request.execution_intent_id] = request
        client_order_id = make_client_order_id(
            session_id=request.metadata.get("session_id", "canary"),
            intent_id=request.execution_intent_id,
            submit_epoch=0,
        )

        try:
            broker_order_id = zorders.place_order(self._write_client, request)
        except Exception:
            # Leave pending — recovery must query broker, never blind resubmit
            raise

        self._pending_intents.pop(request.execution_intent_id, None)
        self._place_calls += 1
        if self.simulated:
            self._simulated_submissions += 1
        else:
            self._live_orders += 1

        self._intent_store.register_submit(
            execution_intent_id=request.execution_intent_id,
            broker_order_id=broker_order_id,
            client_order_id=client_order_id,
            symbol=request.symbol,
            state=BrokerOrderState.SUBMITTED.value,
        )
        return {
            "broker_order_id": broker_order_id,
            "client_order_id": client_order_id,
            "idempotent_replay": False,
            "state": BrokerOrderState.SUBMITTED.value,
            "simulated": self.simulated,
        }

    def get_order_status(self, broker_order_id: str) -> dict[str, Any]:
        if self._write_client is None:
            raise RuntimeError("broker_not_connected")
        view = zorders.get_order(self._write_client, broker_order_id=broker_order_id)
        return {
            "broker_order_id": view.broker_order_id,
            "symbol": view.symbol,
            "quantity": view.quantity,
            "filled_quantity": view.filled_quantity,
            "state": view.state.value if hasattr(view.state, "value") else str(view.state),
            "avg_price": view.avg_price,
        }

    def cancel_order(self, *args: Any, **kwargs: Any) -> None:
        # Not part of unrestricted API — canary does not expose free cancel
        raise BrokerWriteForbidden("phase16b_cancel_not_in_canary_surface")

    def modify_order(self, *args: Any, **kwargs: Any) -> None:
        raise BrokerWriteForbidden("phase16b_modify_not_in_canary_surface")


def build_canary_broker(
    *,
    transport: KiteTransport | None = None,
    force_mock: bool = True,
    simulated: bool | None = None,
    intent_store: ExecutionIntentStore | None = None,
) -> ZerodhaCanaryBroker:
    if force_mock or transport is not None:
        t = transport or build_mock_kite_transport()
        creds = ZerodhaCredentials(
            api_key="mock",
            api_secret="mock",
            access_token="mock",
            env=ZerodhaEnv.SANDBOX,
        )
        return ZerodhaCanaryBroker(
            credentials=creds,
            transport=t,
            simulated=True if simulated is None else simulated,
            intent_store=intent_store,
        )
    raise RuntimeError("real_canary_broker_requires_explicit_factory_path")


def make_broker_order_request(
    *,
    intent_id: str,
    symbol: str,
    side: str,
    quantity: int,
    order_type: str = "MARKET",
    product: str = "CNC",
    session_id: str = "canary",
) -> BrokerOrderRequest:
    return BrokerOrderRequest(
        execution_intent_id=intent_id,
        instrument_id=f"NSE:{symbol}",
        exchange="NSE",
        symbol=symbol,
        side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
        quantity=int(quantity),
        order_type=OrderType.MARKET if order_type.upper() == "MARKET" else OrderType.LIMIT,
        product=product,
        tag=intent_id[:20],
        metadata={"session_id": session_id},
    )

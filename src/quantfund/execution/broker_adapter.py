"""BrokerAdapter protocol and canonical request/response models.

Never expose raw broker SDK objects. Phase 9 v1: MockBroker only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from quantfund.execution.capabilities import BrokerCapabilities
from quantfund.execution.live_orders import BrokerOrderState
from quantfund.trading.models import OrderSide, OrderType


class BrokerHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    connected: bool
    degraded: bool = False
    reason: str | None = None
    server_time: datetime | None = None
    adapter_id: str = "unknown"


class SubmitOrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_order_id: str
    symbol: str
    instrument_id: str | None = None
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    session_id: str
    intent_id: str
    idempotency_key: str
    ref_price: float | None = None


class SubmitOrderResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_order_id: str
    broker_order_id: str | None = None
    state: BrokerOrderState
    reject_reason: str | None = None
    filled_quantity: float = 0.0
    avg_price: float | None = None
    dry_run: bool = False


class CancelOrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_order_id: str
    broker_order_id: str | None = None
    session_id: str


class CancelOrderResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_order_id: str
    state: BrokerOrderState
    reject_reason: str | None = None


class GetOrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_order_id: str
    broker_order_id: str | None = None


class BrokerOrderView(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_order_id: str
    broker_order_id: str | None = None
    symbol: str
    side: OrderSide
    quantity: float
    filled_quantity: float = 0.0
    state: BrokerOrderState
    avg_price: float | None = None
    updated_at: datetime | None = None


class GetOpenOrdersRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str | None = None


class BrokerPositionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    instrument_id: str | None = None
    quantity: float
    average_entry_price: float = 0.0


class BrokerCashView(BaseModel):
    model_config = ConfigDict(frozen=True)

    cash: float
    currency: str = "INR"
    as_of: datetime | None = None


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str


class BrokerReconcileSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    positions: list[BrokerPositionView] = Field(default_factory=list)
    cash: BrokerCashView
    open_orders: list[BrokerOrderView] = Field(default_factory=list)


@runtime_checkable
class BrokerAdapter(Protocol):
    """Minimal broker boundary. Implementations must not leak SDK types."""

    @property
    def adapter_id(self) -> str: ...

    def capabilities(self) -> BrokerCapabilities: ...

    def connect(self) -> BrokerHealth: ...

    def disconnect(self) -> None: ...

    def health(self) -> BrokerHealth: ...

    def submit_order(self, request: SubmitOrderRequest) -> SubmitOrderResponse: ...

    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResponse: ...

    def get_order(self, request: GetOrderRequest) -> BrokerOrderView: ...

    def get_open_orders(self, request: GetOpenOrdersRequest) -> list[BrokerOrderView]: ...

    def get_positions(self) -> list[BrokerPositionView]: ...

    def get_cash(self) -> BrokerCashView: ...

    def reconcile(self, request: ReconcileRequest) -> BrokerReconcileSnapshot: ...


ALLOWED_BROKER_ADAPTER_IDS = frozenset({"mock", "mock_broker", "MockBrokerAdapter"})


def assert_mock_only(adapter_id: str) -> None:
    """Phase 9 v1: any non-mock broker selection fails closed."""
    if adapter_id not in ALLOWED_BROKER_ADAPTER_IDS:
        raise ValueError(
            f"real_broker_forbidden_in_phase9: adapter_id={adapter_id!r}. "
            "Only MockBroker is allowed. Real orders sent must remain 0."
        )

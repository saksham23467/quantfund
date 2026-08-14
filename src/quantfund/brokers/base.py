"""Provider-neutral broker execution adapter (Phase 9B).

Zerodha-specific types must not leak above this boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quantfund.execution.broker_adapter import (
    BrokerCashView,
    BrokerHealth,
    BrokerOrderView,
    BrokerPositionView,
    BrokerReconcileSnapshot,
)
from quantfund.execution.live_orders import BrokerOrderState
from quantfund.trading.models import OrderSide, OrderType


class BrokerOrderRequest(BaseModel):
    """Internal order request — never a Kite SDK object."""

    model_config = ConfigDict(frozen=True)

    execution_intent_id: str
    instrument_id: str
    exchange: str
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    price: float | None = None
    trigger_price: float | None = None
    product: str = "CNC"
    validity: str = "DAY"
    tag: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrokerFill(BaseModel):
    """Fill created only from broker-confirmed trades."""

    model_config = ConfigDict(frozen=True)

    fill_id: str
    broker_trade_id: str
    broker_order_id: str
    instrument_id: str
    symbol: str
    quantity: float
    price: float
    timestamp: datetime
    side: OrderSide
    fees: float | None = None
    provenance: str = "broker"


class BrokerHoldingsView(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    quantity: float
    average_price: float = 0.0
    instrument_id: str | None = None


class BrokerExecutionAdapter(ABC):
    """Neutral broker boundary used by ExecutionRouter / LiveExecutionGuard."""

    @property
    @abstractmethod
    def adapter_id(self) -> str: ...

    @abstractmethod
    def connect(self) -> BrokerHealth: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def health(self) -> BrokerHealth: ...

    @abstractmethod
    def place_order(self, request: BrokerOrderRequest) -> BrokerOrderView: ...

    @abstractmethod
    def modify_order(
        self,
        *,
        broker_order_id: str,
        quantity: int | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
        order_type: OrderType | None = None,
    ) -> BrokerOrderView: ...

    @abstractmethod
    def cancel_order(self, *, broker_order_id: str) -> BrokerOrderView: ...

    @abstractmethod
    def get_order(self, *, broker_order_id: str) -> BrokerOrderView: ...

    @abstractmethod
    def get_orders(self) -> list[BrokerOrderView]: ...

    @abstractmethod
    def get_trades(self) -> list[BrokerFill]: ...

    @abstractmethod
    def get_positions(self) -> list[BrokerPositionView]: ...

    @abstractmethod
    def get_holdings(self) -> list[BrokerHoldingsView]: ...

    @abstractmethod
    def reconcile(self, *, session_id: str) -> BrokerReconcileSnapshot: ...

    def get_cash(self) -> BrokerCashView:
        return BrokerCashView(cash=0.0)


class UnsupportedBrokerOrderError(ValueError):
    """Fail closed on unsupported product/exchange/order type."""


def assert_supported_nse_equity_cnc(request: BrokerOrderRequest) -> None:
    if request.exchange.upper() != "NSE":
        raise UnsupportedBrokerOrderError(f"unsupported_exchange:{request.exchange}")
    if request.product.upper() != "CNC":
        raise UnsupportedBrokerOrderError(f"unsupported_product:{request.product}")
    if request.validity.upper() != "DAY":
        raise UnsupportedBrokerOrderError(f"unsupported_validity:{request.validity}")
    if request.order_type not in {OrderType.MARKET, OrderType.LIMIT}:
        raise UnsupportedBrokerOrderError(f"unsupported_order_type:{request.order_type}")
    if request.order_type == OrderType.LIMIT and (
        request.price is None or request.price <= 0
    ):
        raise UnsupportedBrokerOrderError("limit_requires_positive_price")
    if request.quantity <= 0:
        raise UnsupportedBrokerOrderError("quantity_must_be_positive")
    if request.side not in {OrderSide.BUY, OrderSide.SELL}:
        raise UnsupportedBrokerOrderError(f"unsupported_side:{request.side}")

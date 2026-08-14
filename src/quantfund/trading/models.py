"""Typed models for the Signal → Order → Fill → Position lifecycle.

Strategies may create Signal or Order intents only.
Only the broker simulator may create Fill objects.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Signal(BaseModel):
    """Strategy decision at a point in time. Not an executable order."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    symbol: str
    action: SignalAction
    strength: float = 1.0
    target_quantity: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"  # broker adapters; backtest path remains MARKET-centric


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SCHEDULED = "SCHEDULED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class Order(BaseModel):
    """Intended order produced from a signal; not yet a fill."""

    model_config = ConfigDict(frozen=False)

    order_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    status: OrderStatus = OrderStatus.PENDING
    signal_timestamp: datetime | None = None
    scheduled_execution_time: datetime | None = None
    reject_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("order quantity must be positive")
        return float(value)


class Fill(BaseModel):
    """Executed trade created only by the broker simulator."""

    model_config = ConfigDict(frozen=True)

    fill_id: str = Field(default_factory=lambda: uuid4().hex)
    order_id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    slippage_per_unit: float
    transaction_cost: float
    gross_value: float
    net_cash_delta: float

    @field_validator("quantity", "price")
    @classmethod
    def positive_values(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("fill quantity and price must be positive")
        return float(value)


class Position(BaseModel):
    """Open position state for a symbol. Short selling is not supported in M1."""

    model_config = ConfigDict(frozen=False)

    symbol: str
    quantity: float = 0.0
    average_entry_price: float = 0.0

    @property
    def market_value(self) -> float:
        """Requires mark price; use portfolio helpers for valuation."""
        raise NotImplementedError("Use Portfolio.position_market_value(symbol, price)")

    def is_flat(self) -> bool:
        return self.quantity == 0

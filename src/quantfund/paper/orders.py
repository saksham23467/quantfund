"""Paper-local order intents and PaperOrderStatus state machine."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quantfund.paper.models import deterministic_id
from quantfund.trading.models import Order, OrderSide, OrderStatus, OrderType, Signal


class PaperOrderStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


# Legal directed transitions (fail closed otherwise).
_ALLOWED: dict[PaperOrderStatus, frozenset[PaperOrderStatus]] = {
    PaperOrderStatus.CREATED: frozenset(
        {PaperOrderStatus.VALIDATED, PaperOrderStatus.REJECTED}
    ),
    PaperOrderStatus.VALIDATED: frozenset(
        {PaperOrderStatus.ACCEPTED, PaperOrderStatus.REJECTED}
    ),
    PaperOrderStatus.ACCEPTED: frozenset(
        {
            PaperOrderStatus.PARTIALLY_FILLED,
            PaperOrderStatus.FILLED,
            PaperOrderStatus.CANCELLED,
            PaperOrderStatus.EXPIRED,
            PaperOrderStatus.REJECTED,  # e.g. insufficient cash at fill time
        }
    ),
    PaperOrderStatus.PARTIALLY_FILLED: frozenset(
        {
            PaperOrderStatus.FILLED,
            PaperOrderStatus.CANCELLED,
            PaperOrderStatus.EXPIRED,
        }
    ),
    PaperOrderStatus.FILLED: frozenset(),
    PaperOrderStatus.REJECTED: frozenset(),
    PaperOrderStatus.CANCELLED: frozenset(),
    PaperOrderStatus.EXPIRED: frozenset(),
}


BACKTEST_STATUS_MAP: dict[PaperOrderStatus, OrderStatus] = {
    PaperOrderStatus.CREATED: OrderStatus.PENDING,
    PaperOrderStatus.VALIDATED: OrderStatus.PENDING,
    PaperOrderStatus.ACCEPTED: OrderStatus.SCHEDULED,
    PaperOrderStatus.PARTIALLY_FILLED: OrderStatus.ACCEPTED,
    PaperOrderStatus.FILLED: OrderStatus.FILLED,
    PaperOrderStatus.REJECTED: OrderStatus.REJECTED,
    PaperOrderStatus.CANCELLED: OrderStatus.CANCELLED,
    PaperOrderStatus.EXPIRED: OrderStatus.CANCELLED,
}


class InvalidPaperOrderTransition(ValueError):
    """Raised when an illegal PaperOrderStatus transition is attempted."""


class OrderIntent(BaseModel):
    """Paper-validated intent wrapping a trading.Order."""

    model_config = ConfigDict(frozen=False)

    intent_id: str
    session_id: str
    order: Order
    status: PaperOrderStatus = PaperOrderStatus.CREATED
    filled_quantity: float = 0.0
    reject_reason: str | None = None
    signal_timestamp: datetime | None = None
    scheduled_execution_seq: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def remaining_quantity(self) -> float:
        return max(0.0, self.order.quantity - self.filled_quantity)

    def transition(self, new_status: PaperOrderStatus, *, reason: str | None = None) -> None:
        allowed = _ALLOWED.get(self.status, frozenset())
        if new_status not in allowed:
            raise InvalidPaperOrderTransition(
                f"invalid transition {self.status.value} → {new_status.value} "
                f"for intent {self.intent_id}"
            )
        self.status = new_status
        if reason is not None:
            self.reject_reason = reason
            self.order.reject_reason = reason
        # Mirror compatible backtest status on wrapped order
        self.order.status = BACKTEST_STATUS_MAP[new_status]

    def to_mapping_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "backtest_status": BACKTEST_STATUS_MAP[self.status].value,
            "order_id": self.order.order_id,
            "symbol": self.order.symbol,
            "side": self.order.side.value,
            "quantity": self.order.quantity,
            "filled_quantity": self.filled_quantity,
            "reject_reason": self.reject_reason,
            "scheduled_execution_seq": self.scheduled_execution_seq,
        }


def make_order_intent(
    *,
    session_id: str,
    order: Order,
    signal: Signal | None = None,
    event_seq: int,
) -> OrderIntent:
    """Build OrderIntent with deterministic IDs (does not mutate global uuid defaults)."""
    intent_id = deterministic_id(
        "intent",
        session_id,
        event_seq,
        order.symbol,
        order.side.value,
        f"{order.quantity:.8f}",
        order.timestamp.isoformat(),
        signal.timestamp.isoformat() if signal else "",
    )
    order_id = deterministic_id(
        "order",
        session_id,
        event_seq,
        order.symbol,
        order.side.value,
        f"{order.quantity:.8f}",
        order.timestamp.isoformat(),
    )
    order.order_id = order_id
    order.status = OrderStatus.PENDING
    return OrderIntent(
        intent_id=intent_id,
        session_id=session_id,
        order=order,
        status=PaperOrderStatus.CREATED,
        signal_timestamp=signal.timestamp if signal else order.signal_timestamp,
    )


def validate_order_structurally(order: Order) -> str | None:
    """Return reject reason or None if structurally valid."""
    if order.quantity <= 0:
        return "invalid_quantity"
    if order.order_type != OrderType.MARKET:
        return "unsupported_order_type"
    if order.side not in {OrderSide.BUY, OrderSide.SELL}:
        return "invalid_side"
    if not order.symbol or not str(order.symbol).strip():
        return "missing_symbol"
    return None

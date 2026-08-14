"""Live-local broker order state and deterministic client order IDs.

Do NOT expand shared trading.OrderStatus — BrokerOrderState is live-local only.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BrokerOrderState(str, Enum):
    UNKNOWN = "UNKNOWN"
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    OPEN = "OPEN"  # Phase 9B — broker open/working (alias semantic of ACKNOWLEDGED)
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


TERMINAL_BROKER_STATES = frozenset(
    {
        BrokerOrderState.FILLED,
        BrokerOrderState.CANCELLED,
        BrokerOrderState.REJECTED,
        BrokerOrderState.EXPIRED,
    }
)

# UNKNOWN must never be treated as FILLED
NON_FILL_AMBIGUOUS = frozenset({BrokerOrderState.UNKNOWN, BrokerOrderState.SUBMITTED})


def make_client_order_id(
    *,
    session_id: str,
    intent_id: str,
    submit_epoch: int = 0,
) -> str:
    """Deterministic client order id — never uuid4."""
    payload = f"coid|{session_id}|{intent_id}|{submit_epoch}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class IdempotencyRecord(BaseModel):
    model_config = ConfigDict(frozen=False)

    client_order_id: str
    intent_id: str
    session_id: str
    submit_epoch: int = 0
    state: BrokerOrderState = BrokerOrderState.CREATED
    broker_order_id: str | None = None
    filled_quantity: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class IdempotencyStore:
    """Pre-submit local records — required before any broker interaction."""

    def __init__(self) -> None:
        self._by_client: dict[str, IdempotencyRecord] = {}
        self._by_intent: dict[str, list[str]] = {}

    def get(self, client_order_id: str) -> IdempotencyRecord | None:
        return self._by_client.get(client_order_id)

    def get_for_intent(self, intent_id: str) -> list[IdempotencyRecord]:
        return [self._by_client[c] for c in self._by_intent.get(intent_id, []) if c in self._by_client]

    def put(self, record: IdempotencyRecord) -> None:
        self._by_client[record.client_order_id] = record
        self._by_intent.setdefault(record.intent_id, [])
        if record.client_order_id not in self._by_intent[record.intent_id]:
            self._by_intent[record.intent_id].append(record.client_order_id)

    def can_retry(self, intent_id: str) -> tuple[bool, str]:
        """Blind retry forbidden while any epoch is UNKNOWN/SUBMITTED without terminal."""
        for rec in self.get_for_intent(intent_id):
            if rec.state == BrokerOrderState.UNKNOWN:
                return False, "unknown_broker_state_no_retry"
            if rec.state == BrokerOrderState.SUBMITTED:
                return False, "submit_pending_no_retry"
            if rec.state not in TERMINAL_BROKER_STATES and rec.state not in {
                BrokerOrderState.REJECTED,
            }:
                if rec.state in {
                    BrokerOrderState.ACKNOWLEDGED,
                    BrokerOrderState.OPEN,
                    BrokerOrderState.PARTIALLY_FILLED,
                    BrokerOrderState.CANCEL_PENDING,
                }:
                    return False, f"open_state_{rec.state.value}_no_retry"
        return True, "ok"

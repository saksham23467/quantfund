"""Crash recovery — never blind-resubmit after uncertain broker submit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quantfund.brokers.intent_store import ExecutionIntentStore
from quantfund.phase16b.broker import ZerodhaCanaryBroker


@dataclass
class RecoveryDecision:
    action: str
    resubmit: bool
    broker_order_id: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "resubmit": False,  # hard invariant
            "broker_order_id": self.broker_order_id,
            "detail": self.detail,
        }


def recover_uncertain_submit(
    *,
    intent_id: str,
    broker: ZerodhaCanaryBroker,
    intent_store: ExecutionIntentStore | None = None,
) -> RecoveryDecision:
    """If crash after send / before ack: query broker; never blind resubmit."""
    store = intent_store or broker._intent_store
    rec = store.get(intent_id)
    if rec and rec.broker_order_id:
        return RecoveryDecision(
            action="ALREADY_SUBMITTED",
            resubmit=False,
            broker_order_id=rec.broker_order_id,
            detail="reconcile_existing_order",
        )
    # Pending without broker id — scan broker orders for tag/intent
    try:
        orders = broker.get_orders()
    except Exception as exc:  # noqa: BLE001
        return RecoveryDecision(
            action="HALT_QUERY_FAILED",
            resubmit=False,
            detail=type(exc).__name__,
        )
    for o in orders:
        tag = str(o.get("tag") or "")
        if tag and tag in intent_id:
            return RecoveryDecision(
                action="FOUND_ON_BROKER",
                resubmit=False,
                broker_order_id=str(o.get("order_id")),
                detail="adopt_broker_order",
            )
    # Clear pending so a *new* intentional submit can occur only after operator review
    broker._pending_intents.pop(intent_id, None)
    return RecoveryDecision(
        action="NOT_FOUND_NO_RESUBMIT",
        resubmit=False,
        detail="operator_must_reissue_new_intent",
    )

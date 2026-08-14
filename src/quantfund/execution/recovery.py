"""Restart recovery sketch — load local idempotency, query mock, reconcile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quantfund.execution.broker_adapter import GetOrderRequest
from quantfund.execution.gateway import ExecutionGateway
from quantfund.execution.live_orders import BrokerOrderState


@dataclass
class RecoveryResult:
    recovered: bool
    blocked: bool
    reason: str
    details: dict[str, Any]


def recover_gateway(gateway: ExecutionGateway) -> RecoveryResult:
    """After process restart simulation: reconcile or remain BLOCKED."""
    if not gateway._started:
        return RecoveryResult(False, True, "gateway_not_started", {})

    # Adopt UNKNOWN → never treat as FILLED
    for intent_ids in gateway.idempotency._by_intent.values():
        for cid in intent_ids:
            rec = gateway.idempotency.get(cid)
            if rec and rec.state == BrokerOrderState.UNKNOWN:
                view = gateway.broker.get_order(GetOrderRequest(client_order_id=cid))
                if view.state == BrokerOrderState.FILLED:
                    # Do not silently mark internal FILLED without explicit adopt policy
                    return RecoveryResult(
                        False,
                        True,
                        "unknown_vs_filled_requires_manual_adopt",
                        {"client_order_id": cid},
                    )
                if view.state == BrokerOrderState.UNKNOWN:
                    return RecoveryResult(
                        False, True, "still_unknown_after_query", {"client_order_id": cid}
                    )

    report = gateway.reconcile()
    if not report.ok:
        return RecoveryResult(False, True, "reconciliation_failed", report.to_dict())
    if gateway.kill_switch.is_triggered:
        return RecoveryResult(False, True, "kill_switch_active", {})
    return RecoveryResult(True, False, "recovered", {"reconciliation": "passed"})

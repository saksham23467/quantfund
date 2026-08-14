"""Reconcile internal vs broker state — UNKNOWN never means FILLED."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.execution.broker_adapter import BrokerOrderView, BrokerReconcileSnapshot
from quantfund.execution.live_orders import BrokerOrderState, IdempotencyRecord


@dataclass
class ReconcileIssue:
    code: str
    message: str


@dataclass
class LiveReconcileReport:
    ok: bool
    issues: list[ReconcileIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [{"code": i.code, "message": i.message} for i in self.issues],
        }


def reconcile_live_state(
    *,
    internal_records: list[IdempotencyRecord],
    broker_snapshot: BrokerReconcileSnapshot,
    internal_positions: dict[str, float],
    internal_cash: float,
    allow_cash_epsilon: float = 1e-4,
) -> LiveReconcileReport:
    issues: list[ReconcileIssue] = []
    broker_by_client = {
        o.client_order_id: o for o in _all_broker_orders(broker_snapshot)
    }

    for rec in internal_records:
        view = broker_by_client.get(rec.client_order_id)
        if view is None:
            if rec.state in {
                BrokerOrderState.FILLED,
                BrokerOrderState.ACKNOWLEDGED,
                BrokerOrderState.PARTIALLY_FILLED,
            }:
                issues.append(
                    ReconcileIssue(
                        "missing_broker_order",
                        f"internal {rec.state.value} but broker missing "
                        f"{rec.client_order_id}",
                    )
                )
            continue

        # Critical: internal FILLED + broker UNKNOWN
        if (
            rec.state == BrokerOrderState.FILLED
            and view.state == BrokerOrderState.UNKNOWN
        ):
            issues.append(
                ReconcileIssue(
                    "filled_vs_unknown",
                    "internal FILLED but broker UNKNOWN — never assume fill",
                )
            )

        if (
            rec.state == BrokerOrderState.UNKNOWN
            and view.state == BrokerOrderState.FILLED
        ):
            issues.append(
                ReconcileIssue(
                    "unknown_vs_filled",
                    "internal UNKNOWN but broker FILLED — must adopt carefully",
                )
            )

        if (
            rec.state
            in {
                BrokerOrderState.ACKNOWLEDGED,
                BrokerOrderState.SUBMITTED,
                BrokerOrderState.PARTIALLY_FILLED,
            }
            and view.state == BrokerOrderState.CANCELLED
        ):
            issues.append(
                ReconcileIssue(
                    "open_vs_cancelled",
                    f"internal {rec.state.value} but broker CANCELLED",
                )
            )

        # Never treat UNKNOWN as FILLED
        if view.state == BrokerOrderState.UNKNOWN and rec.state == BrokerOrderState.FILLED:
            pass  # already flagged
        if view.state == BrokerOrderState.UNKNOWN:
            # Ambiguous — block if we claimed a fill quantity
            if rec.filled_quantity > 0:
                issues.append(
                    ReconcileIssue(
                        "unknown_with_internal_fill_qty",
                        "broker UNKNOWN with internal filled_quantity > 0",
                    )
                )

    # Positions
    broker_pos = {p.symbol: p.quantity for p in broker_snapshot.positions}
    for sym, qty in internal_positions.items():
        bq = broker_pos.get(sym, 0.0)
        if abs(qty - bq) > 1e-6:
            issues.append(
                ReconcileIssue(
                    "position_mismatch",
                    f"{sym}: internal={qty} broker={bq}",
                )
            )
    for sym, bq in broker_pos.items():
        if sym not in internal_positions and abs(bq) > 1e-6:
            issues.append(
                ReconcileIssue(
                    "position_mismatch",
                    f"{sym}: internal=0 broker={bq}",
                )
            )

    if abs(internal_cash - broker_snapshot.cash.cash) > allow_cash_epsilon:
        issues.append(
            ReconcileIssue(
                "cash_mismatch",
                f"internal_cash={internal_cash} broker={broker_snapshot.cash.cash}",
            )
        )

    return LiveReconcileReport(ok=len(issues) == 0, issues=issues)


def _all_broker_orders(snapshot: BrokerReconcileSnapshot) -> list[BrokerOrderView]:
    return list(snapshot.open_orders)


def assert_unknown_is_not_filled(state: BrokerOrderState) -> None:
    if state == BrokerOrderState.UNKNOWN:
        raise ValueError("UNKNOWN_is_not_FILLED")

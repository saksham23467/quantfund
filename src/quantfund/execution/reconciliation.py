"""BrokerReconciler — compare local expected vs broker actual (no silent repair)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from quantfund.execution.broker_adapter import (
    BrokerOrderView,
    BrokerPositionView,
    BrokerReconcileSnapshot,
)
from quantfund.execution.live_orders import BrokerOrderState


class ReconcileOutcome(str, Enum):
    MATCH = "MATCH"
    LOCAL_MISSING = "LOCAL_MISSING"
    BROKER_MISSING = "BROKER_MISSING"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    STATUS_MISMATCH = "STATUS_MISMATCH"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    DUPLICATE_FILL = "DUPLICATE_FILL"
    STALE_ORDER = "STALE_ORDER"
    UNEXPECTED_POSITION = "UNEXPECTED_POSITION"
    UNEXPECTED_FILL = "UNEXPECTED_FILL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ReconcileFinding:
    outcome: ReconcileOutcome
    entity: str  # order | fill | position | holding | intent
    key: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "entity": self.entity,
            "key": self.key,
            "detail": self.detail,
        }


@dataclass
class LocalExpectedState:
    orders: list[BrokerOrderView] = field(default_factory=list)
    positions: list[BrokerPositionView] = field(default_factory=list)
    fill_quantities: dict[str, float] = field(default_factory=dict)
    fill_avg_prices: dict[str, float] = field(default_factory=dict)
    fill_ids: list[str] = field(default_factory=list)
    execution_intent_ids: list[str] = field(default_factory=list)
    broker_trade_ids: list[str] = field(default_factory=list)
    now: datetime | None = None
    stale_after_seconds: float = 86_400.0


@dataclass
class BrokerReconcileReport:
    findings: list[ReconcileFinding] = field(default_factory=list)
    matched: bool = False
    fail_closed: bool = True

    @property
    def allows_new_orders(self) -> bool:
        """Fail closed: new orders only when fully matched."""
        return bool(self.matched)

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "fail_closed": self.fail_closed,
            "findings": [f.to_dict() for f in self.findings],
            "silent_repair": False,
            "allows_new_orders": self.allows_new_orders,
        }


class BrokerReconciler:
    """Compare LOCAL EXPECTED vs BROKER ACTUAL. Never silently repairs."""

    def reconcile(
        self,
        local: LocalExpectedState,
        broker: BrokerReconcileSnapshot,
        *,
        broker_orders: list[BrokerOrderView] | None = None,
        broker_trade_ids: list[str] | None = None,
    ) -> BrokerReconcileReport:
        findings: list[ReconcileFinding] = []
        order_list = list(broker_orders or broker.open_orders)
        b_orders: dict[str, BrokerOrderView] = {}
        for o in order_list:
            if not o.broker_order_id:
                continue
            if o.broker_order_id in b_orders:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.DUPLICATE_ORDER,
                        "order",
                        o.broker_order_id,
                        "duplicate broker_order_id in broker snapshot",
                    )
                )
            b_orders[o.broker_order_id] = o

        # local duplicate order ids
        seen_local: set[str] = set()
        for o in local.orders:
            if not o.broker_order_id:
                continue
            if o.broker_order_id in seen_local:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.DUPLICATE_ORDER,
                        "order",
                        o.broker_order_id,
                        "duplicate broker_order_id in local state",
                    )
                )
            seen_local.add(o.broker_order_id)

        # duplicate fill ids
        seen_fills: set[str] = set()
        for fid in local.fill_ids:
            if fid in seen_fills:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.DUPLICATE_FILL,
                        "fill",
                        fid,
                        "duplicate local fill_id",
                    )
                )
            seen_fills.add(fid)

        l_orders = {o.broker_order_id: o for o in local.orders if o.broker_order_id}

        for oid, lo in l_orders.items():
            bo = b_orders.get(oid)
            if bo is None:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.BROKER_MISSING,
                        "order",
                        oid,
                        "local order not present in broker snapshot",
                    )
                )
                continue
            if abs(lo.quantity - bo.quantity) > 1e-9:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.QUANTITY_MISMATCH,
                        "order",
                        oid,
                        f"local_qty={lo.quantity} broker_qty={bo.quantity}",
                    )
                )
            if lo.state != bo.state and not (
                lo.state == BrokerOrderState.ACKNOWLEDGED and bo.state == BrokerOrderState.OPEN
            ):
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.STATUS_MISMATCH,
                        "order",
                        oid,
                        f"local={lo.state.value} broker={bo.state.value}",
                    )
                )
            if lo.state == BrokerOrderState.UNKNOWN or bo.state == BrokerOrderState.UNKNOWN:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.UNKNOWN,
                        "order",
                        oid,
                        "unknown broker status requires human review",
                    )
                )
            # stale open order
            now = local.now or datetime.now(timezone.utc)
            ts = lo.updated_at or bo.updated_at
            if (
                ts is not None
                and lo.state
                in {
                    BrokerOrderState.OPEN,
                    BrokerOrderState.SUBMITTED,
                    BrokerOrderState.ACKNOWLEDGED,
                    BrokerOrderState.PARTIALLY_FILLED,
                }
                and (now - ts).total_seconds() > local.stale_after_seconds
            ):
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.STALE_ORDER,
                        "order",
                        oid,
                        f"open longer than {local.stale_after_seconds}s",
                    )
                )

        for oid, lf_qty in local.fill_quantities.items():
            bo = b_orders.get(oid)
            if bo is None:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.BROKER_MISSING,
                        "fill",
                        oid,
                        "local fill order missing on broker",
                    )
                )
                continue
            if abs(lf_qty - bo.filled_quantity) > 1e-9:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.QUANTITY_MISMATCH,
                        "fill",
                        oid,
                        f"local_fill={lf_qty} broker_fill={bo.filled_quantity}",
                    )
                )
            lp = local.fill_avg_prices.get(oid)
            if lp is not None and bo.avg_price is not None and abs(lp - bo.avg_price) > 1e-6:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.PRICE_MISMATCH,
                        "fill",
                        oid,
                        f"local_avg={lp} broker_avg={bo.avg_price}",
                    )
                )

        for oid, bo in b_orders.items():
            if oid not in l_orders and oid not in local.fill_quantities:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.LOCAL_MISSING,
                        "order",
                        oid,
                        "broker order not in local expected state",
                    )
                )
            if bo.filled_quantity > 0 and oid not in local.fill_quantities:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.UNEXPECTED_FILL,
                        "fill",
                        oid,
                        "broker reports fills without local fill record",
                    )
                )

        # unexpected broker trades
        for tid in broker_trade_ids or []:
            if tid not in set(local.broker_trade_ids):
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.UNEXPECTED_FILL,
                        "fill",
                        tid,
                        "broker trade_id not in local ledger",
                    )
                )

        # positions
        l_pos = {p.symbol: p for p in local.positions}
        b_pos = {p.symbol: p for p in broker.positions}
        for sym, lp in l_pos.items():
            bp = b_pos.get(sym)
            if bp is None:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.BROKER_MISSING,
                        "position",
                        sym,
                        "local position missing on broker",
                    )
                )
                continue
            if abs(lp.quantity - bp.quantity) > 1e-9:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.QUANTITY_MISMATCH,
                        "position",
                        sym,
                        f"local={lp.quantity} broker={bp.quantity}",
                    )
                )
            if abs(lp.average_entry_price - bp.average_entry_price) > 1e-6:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.PRICE_MISMATCH,
                        "position",
                        sym,
                        f"local_avg={lp.average_entry_price} broker_avg={bp.average_entry_price}",
                    )
                )
        for sym, bp in b_pos.items():
            if sym not in l_pos:
                findings.append(
                    ReconcileFinding(
                        ReconcileOutcome.UNEXPECTED_POSITION
                        if bp.quantity != 0
                        else ReconcileOutcome.LOCAL_MISSING,
                        "position",
                        sym,
                        "broker position missing locally",
                    )
                )

        if not findings:
            findings.append(
                ReconcileFinding(
                    ReconcileOutcome.MATCH, "session", "*", "all compared fields match"
                )
            )
        matched = all(f.outcome == ReconcileOutcome.MATCH for f in findings)
        return BrokerReconcileReport(
            findings=findings, matched=matched, fail_closed=not matched
        )

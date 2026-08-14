"""Zerodha-side snapshot helpers for BrokerReconciler."""

from __future__ import annotations

from quantfund.brokers.zerodha.client import KiteClient
from quantfund.brokers.zerodha.orders import get_orders
from quantfund.brokers.zerodha.portfolio import get_cash, get_positions
from quantfund.execution.broker_adapter import BrokerReconcileSnapshot, ReconcileRequest


def fetch_broker_snapshot(client: KiteClient, request: ReconcileRequest) -> BrokerReconcileSnapshot:
    _ = request.session_id
    return BrokerReconcileSnapshot(
        positions=get_positions(client),
        cash=get_cash(client),
        open_orders=[
            o
            for o in get_orders(client)
            if o.state.value
            not in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
        ],
    )

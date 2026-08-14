"""Zerodha order placement / lifecycle — fills only from trade responses."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from quantfund.brokers.base import BrokerFill, BrokerOrderRequest
from quantfund.brokers.zerodha.client import KiteClient
from quantfund.brokers.zerodha.mapper import (
    map_kite_status,
    refine_state_with_fills,
    side_from_kite,
    to_kite_order_params,
)
from quantfund.execution.broker_adapter import BrokerOrderView
from quantfund.execution.live_orders import BrokerOrderState
from quantfund.trading.models import OrderSide


def place_order(client: KiteClient, request: BrokerOrderRequest) -> str:
    """Place order; returns broker_order_id. Does NOT create a fill."""
    params = to_kite_order_params(request)
    resp = client.post("/orders/regular", data=params)
    oid = (resp.get("data") or {}).get("order_id")
    if not oid:
        raise RuntimeError("kite_place_order_missing_order_id")
    return str(oid)


def modify_order(
    client: KiteClient,
    *,
    broker_order_id: str,
    quantity: int | None = None,
    price: float | None = None,
    trigger_price: float | None = None,
    order_type: str | None = None,
) -> str:
    data: dict[str, Any] = {}
    if quantity is not None:
        data["quantity"] = quantity
    if price is not None:
        data["price"] = price
    if trigger_price is not None:
        data["trigger_price"] = trigger_price
    if order_type is not None:
        data["order_type"] = order_type
    resp = client.put(f"/orders/regular/{broker_order_id}", data=data)
    return str((resp.get("data") or {}).get("order_id") or broker_order_id)


def cancel_order(client: KiteClient, *, broker_order_id: str) -> str:
    resp = client.delete(f"/orders/regular/{broker_order_id}")
    return str((resp.get("data") or {}).get("order_id") or broker_order_id)


def _view_from_kite_order(raw: dict[str, Any], *, client_order_id: str = "") -> BrokerOrderView:
    qty = float(raw.get("quantity") or 0)
    filled = float(raw.get("filled_quantity") or 0)
    state = map_kite_status(raw.get("status"))
    state = refine_state_with_fills(state, quantity=qty, filled_quantity=filled)
    side_raw = raw.get("transaction_type") or "BUY"
    try:
        side = side_from_kite(str(side_raw))
    except Exception:  # noqa: BLE001
        side = OrderSide.BUY
    return BrokerOrderView(
        client_order_id=client_order_id or str(raw.get("tag") or raw.get("order_id") or ""),
        broker_order_id=str(raw.get("order_id") or ""),
        symbol=str(raw.get("tradingsymbol") or ""),
        side=side,
        quantity=qty,
        filled_quantity=filled,
        state=state,
        avg_price=float(raw["average_price"]) if raw.get("average_price") else None,
        updated_at=datetime.now(timezone.utc),
    )


def get_order(client: KiteClient, *, broker_order_id: str) -> BrokerOrderView:
    resp = client.get(f"/orders/{broker_order_id}")
    data = resp.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}
    return _view_from_kite_order(data)


def get_orders(client: KiteClient) -> list[BrokerOrderView]:
    resp = client.get("/orders")
    data = resp.get("data") or []
    return [_view_from_kite_order(row) for row in data]


def trades_to_fills(
    trades: list[dict[str, Any]],
    *,
    provenance: str = "zerodha",
) -> list[BrokerFill]:
    fills: list[BrokerFill] = []
    for t in trades:
        trade_id = str(t.get("trade_id") or t.get("fill_id") or "")
        order_id = str(t.get("order_id") or "")
        if not trade_id or not order_id:
            continue
        qty = float(t.get("quantity") or 0)
        price = float(t.get("average_price") or t.get("price") or 0)
        if qty <= 0 or price <= 0:
            continue
        try:
            side = side_from_kite(str(t.get("transaction_type") or "BUY"))
        except Exception:  # noqa: BLE001
            continue
        ts_raw = t.get("fill_timestamp") or t.get("order_timestamp")
        if isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            ts = datetime.now(timezone.utc)
        symbol = str(t.get("tradingsymbol") or "")
        fills.append(
            BrokerFill(
                fill_id=f"zf:{trade_id}",
                broker_trade_id=trade_id,
                broker_order_id=order_id,
                instrument_id=f"NSE:{symbol}" if symbol else "UNKNOWN",
                symbol=symbol,
                quantity=qty,
                price=price,
                timestamp=ts,
                side=side,
                fees=float(t["charge"]) if t.get("charge") is not None else None,
                provenance=provenance,
            )
        )
    return fills


def get_trades(client: KiteClient) -> list[BrokerFill]:
    resp = client.get("/trades")
    data = resp.get("data") or []
    return trades_to_fills(data)


def get_order_trades(client: KiteClient, *, broker_order_id: str) -> list[BrokerFill]:
    resp = client.get(f"/orders/{broker_order_id}/trades")
    data = resp.get("data") or []
    return trades_to_fills(data)


def place_success_is_not_fill(state: BrokerOrderState) -> bool:
    """Invariant helper — SUBMITTED/OPEN after place must not be treated as FILLED."""
    return state != BrokerOrderState.FILLED

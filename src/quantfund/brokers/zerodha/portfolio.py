"""Zerodha positions / holdings / cash views."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from quantfund.brokers.base import BrokerHoldingsView
from quantfund.brokers.zerodha.client import KiteClient
from quantfund.execution.broker_adapter import BrokerCashView, BrokerPositionView


def get_positions(client: KiteClient) -> list[BrokerPositionView]:
    resp = client.get("/portfolio/positions")
    data = resp.get("data") or {}
    net = data.get("net") if isinstance(data, dict) else data
    out: list[BrokerPositionView] = []
    for row in net or []:
        symbol = str(row.get("tradingsymbol") or "")
        qty = float(row.get("quantity") or 0)
        out.append(
            BrokerPositionView(
                symbol=symbol,
                instrument_id=f"NSE:{symbol}" if symbol else None,
                quantity=qty,
                average_entry_price=float(row.get("average_price") or 0.0),
            )
        )
    return out


def get_holdings(client: KiteClient) -> list[BrokerHoldingsView]:
    resp = client.get("/portfolio/holdings")
    data = resp.get("data") or []
    out: list[BrokerHoldingsView] = []
    for row in data:
        symbol = str(row.get("tradingsymbol") or "")
        out.append(
            BrokerHoldingsView(
                symbol=symbol,
                exchange=str(row.get("exchange") or "NSE"),
                quantity=float(row.get("quantity") or 0),
                average_price=float(row.get("average_price") or 0.0),
                instrument_id=f"NSE:{symbol}" if symbol else None,
            )
        )
    return out


def get_cash(client: KiteClient, margins: dict[str, Any] | None = None) -> BrokerCashView:
    """Cash from margins payload when available; else 0 (read-only safe default)."""
    cash = 0.0
    if margins:
        eq = margins.get("equity") or margins
        avail = eq.get("available") if isinstance(eq, dict) else None
        if isinstance(avail, dict):
            cash = float(avail.get("cash") or avail.get("live_balance") or 0.0)
        elif isinstance(eq, dict):
            cash = float(eq.get("net") or 0.0)
    return BrokerCashView(cash=cash, currency="INR", as_of=datetime.now(timezone.utc))

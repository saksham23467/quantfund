"""Test-only Zerodha FakeKiteTransport seeding — NEVER used on the live real-time path.

Explicitly gated by QUANTFUND_PHASE21_ALLOW_MOCK / force_mock.
Produces Zerodha-shaped candles (not yfinance, not synthetic research labels).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from quantfund.brokers.zerodha.client import FakeKiteTransport
from quantfund.phase16a.mock_transport import build_mock_kite_transport


def build_phase21_mock_transport(
    *,
    symbol: str = "RELIANCE",
    n_days: int = 45,
    start: date | None = None,
    base_price: float = 2500.0,
) -> Any:
    """Seed FakeKiteTransport with a multi-day daily candle series for unit tests."""
    transport = build_mock_kite_transport(symbol=symbol, include_orders=False)
    # Unwrap profile wrapper to seed candles on inner FakeKiteTransport
    inner: FakeKiteTransport = getattr(transport, "inner", transport)
    start = start or date(2024, 1, 2)
    candles: list[list[Any]] = []
    px = base_price
    # n_days = target trading sessions; walk calendar until filled
    d = start
    i = 0
    while len(candles) < n_days:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        o = px
        c = px * (1.0 + 0.002 * ((i % 7) - 3))
        h = max(o, c) * 1.005
        l = min(o, c) * 0.995
        ts = datetime(d.year, d.month, d.day, 15, 30, tzinfo=timezone.utc)
        candles.append([ts.isoformat(), o, h, l, c, 10000.0 + i * 10])
        px = c
        i += 1
        d += timedelta(days=1)
    inner.candles = candles
    # Keep last quote aligned
    if candles:
        last = candles[-1]
        transport.quotes = {
            f"NSE:{symbol}": {
                "last_price": float(last[4]),
                "ohlc": {
                    "open": float(last[1]),
                    "high": float(last[2]),
                    "low": float(last[3]),
                    "close": float(last[4]),
                },
                "volume": float(last[5]),
                "timestamp": last[0],
            }
        }
        inner.quotes = transport.quotes
    return transport

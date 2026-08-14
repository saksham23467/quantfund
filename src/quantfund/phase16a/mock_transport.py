"""CI/demo FakeKiteTransport factory — never contacts Zerodha."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from quantfund.brokers.zerodha.client import FakeKiteTransport


def build_mock_kite_transport(
    *,
    symbol: str = "RELIANCE",
    account_id: str = "MOCK_USER_001",
    cash: float = 100_000.0,
    position_qty: float = 0.0,
    include_orders: bool = True,
) -> FakeKiteTransport:
    """Seeded mock transport for Phase 16A demos and unit tests."""
    fake = FakeKiteTransport()
    now = datetime.now(timezone.utc).isoformat()
    fake.instruments = [
        {
            "instrument_token": 738561,
            "exchange": "NSE",
            "tradingsymbol": symbol,
            "name": symbol,
            "isin": "INE002A01018",
        }
    ]
    fake.quotes = {
        f"NSE:{symbol}": {
            "last_price": 2500.0,
            "ohlc": {
                "open": 2480.0,
                "high": 2520.0,
                "low": 2470.0,
                "close": 2500.0,
            },
            "volume": 10_000,
            "timestamp": now,
        }
    }
    fake.candles = [[now, 2480, 2520, 2470, 2500, 10000]]
    if position_qty:
        fake.positions = [
            {
                "tradingsymbol": symbol,
                "quantity": position_qty,
                "average_price": 2400.0,
                "exchange": "NSE",
            }
        ]
    fake.holdings = []
    if include_orders:
        fake.orders = {
            "mock-ord-1": {
                "order_id": "mock-ord-1",
                "status": "COMPLETE",
                "tradingsymbol": symbol,
                "exchange": "NSE",
                "transaction_type": "BUY",
                "quantity": 0,
                "filled_quantity": 0,
                "average_price": 0.0,
                "order_type": "MARKET",
                "product": "CNC",
            }
        }
        fake.trades = []
    # Attach profile/margins via subclassing request — wrap
    return _ProfileMarginsTransport(fake, account_id=account_id, cash=cash)


class _ProfileMarginsTransport:
    """Decorator adding /user/profile and /user/margins to FakeKiteTransport."""

    def __init__(
        self, inner: FakeKiteTransport, *, account_id: str, cash: float
    ) -> None:
        self.inner = inner
        self.account_id = account_id
        self.cash = cash
        # expose attributes tests may inspect
        self.place_calls = inner.place_calls
        self.orders = inner.orders
        self.trades = inner.trades
        self.positions = inner.positions
        self.holdings = inner.holdings
        self.instruments = inner.instruments
        self.quotes = inner.quotes
        self.fail_next = None

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.fail_next:
            msg = self.fail_next
            self.fail_next = None
            raise RuntimeError(msg)
        if self.inner.fail_next:
            msg = self.inner.fail_next
            self.inner.fail_next = None
            raise RuntimeError(msg)
        if "/user/profile" in url:
            return {
                "status": "success",
                "data": {
                    "user_id": self.account_id,
                    "user_name": "MOCK",
                    "email": "mock@example.invalid",
                },
            }
        if "/user/margins" in url:
            return {
                "status": "success",
                "data": {
                    "equity": {
                        "available": {"cash": self.cash, "live_balance": self.cash},
                        "net": self.cash,
                    }
                },
            }
        resp = self.inner.request(
            method=method, url=url, headers=headers, data=data, params=params
        )
        self.place_calls = self.inner.place_calls
        return resp

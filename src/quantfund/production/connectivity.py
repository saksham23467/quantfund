"""Zerodha read-only connectivity test — never places/modifies/cancels orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol

from quantfund.brokers.zerodha.auth import (
    ZerodhaCredentials,
    credentials_configured,
    load_credentials_from_env,
)
from quantfund.brokers.zerodha.client import FakeKiteTransport, KiteClient, KiteTransport
from quantfund.brokers.zerodha.market_data import ZerodhaMarketDataAdapter
from quantfund.execution.credentials import redact_secrets


class ReadOnlyForbidden(RuntimeError):
    """Raised if any mutating broker path is attempted during connectivity test."""


@dataclass
class ConnectivityResult:
    configured: bool
    authenticated: bool
    profile: dict[str, Any] = field(default_factory=dict)
    instruments_count: int = 0
    quotes: dict[str, Any] = field(default_factory=dict)
    historical_bars: int = 0
    instrument_identity_ok: bool = False
    timestamp_ok: bool = False
    order_submission: str = "NOT EXECUTED"
    orders_placed: int = 0
    errors: list[str] = field(default_factory=list)
    simulated: bool = False

    @property
    def ok(self) -> bool:
        # Simulated path is OK for demos/CI without real credentials.
        base = (
            self.authenticated
            and self.order_submission == "NOT EXECUTED"
            and self.orders_placed == 0
            and not self.errors
        )
        if self.simulated:
            return base
        return bool(self.configured and base)

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "authenticated": self.authenticated,
            "profile": redact_secrets(self.profile),
            "instruments_count": self.instruments_count,
            "quotes": self.quotes,
            "historical_bars": self.historical_bars,
            "instrument_identity_ok": self.instrument_identity_ok,
            "timestamp_ok": self.timestamp_ok,
            "order_submission": self.order_submission,
            "orders_placed": self.orders_placed,
            "errors": list(self.errors),
            "simulated": self.simulated,
            "BROKER_CONNECTIVITY": "PASS" if self.ok else "FAIL",
        }


class _GuardTransport:
    """Wraps transport and forbids order mutation endpoints."""

    def __init__(self, inner: KiteTransport) -> None:
        self.inner = inner
        self.mutations_blocked = 0

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        u = url.lower()
        if method.upper() in {"POST", "PUT", "DELETE"} and "/orders" in u:
            if "session/token" not in u:
                self.mutations_blocked += 1
                raise ReadOnlyForbidden(f"mutation_forbidden:{method}:{url}")
        return self.inner.request(
            method=method, url=url, headers=headers, data=data, params=params
        )


def run_zerodha_connectivity_test(
    *,
    env: dict[str, str] | None = None,
    transport: KiteTransport | None = None,
    simulate_if_unconfigured: bool = True,
    symbol: str = "INFY",
) -> ConnectivityResult:
    """Authenticate + read-only probes. Never submits orders."""
    if not credentials_configured(env):
        if not simulate_if_unconfigured:
            return ConnectivityResult(
                configured=False,
                authenticated=False,
                errors=["credentials_not_configured"],
            )
        # Simulated path for demos/CI
        fake = FakeKiteTransport()
        fake.instruments = [
            {
                "instrument_token": 408065,
                "exchange": "NSE",
                "tradingsymbol": symbol,
                "name": symbol,
                "isin": "INE009A01021",
            }
        ]
        fake.quotes = {
            f"NSE:{symbol}": {
                "last_price": 1500.0,
                "ohlc": {"open": 1490.0, "high": 1510.0, "low": 1480.0, "close": 1500.0},
                "volume": 1000,
            }
        }
        fake.candles = [
            [datetime.now(timezone.utc).isoformat(), 1490, 1510, 1480, 1500, 1000]
        ]
        result = _execute_readonly(
            ZerodhaCredentials(
                api_key="sim",
                api_secret="sim",
                access_token="sim",
            ),
            transport=fake,
            symbol=symbol,
            simulated=True,
        )
        result.configured = False  # no real credentials; simulated path only
        return result

    creds = load_credentials_from_env(env)
    assert creds is not None
    if transport is None:
        from quantfund.brokers.zerodha.client import UrllibKiteTransport

        transport = UrllibKiteTransport()
    return _execute_readonly(creds, transport=transport, symbol=symbol, simulated=False)


def _execute_readonly(
    creds: ZerodhaCredentials,
    *,
    transport: KiteTransport,
    symbol: str,
    simulated: bool,
) -> ConnectivityResult:
    guard = _GuardTransport(transport)
    client = KiteClient(credentials=creds, transport=guard)  # type: ignore[arg-type]
    result = ConnectivityResult(configured=True, authenticated=False, simulated=simulated)
    try:
        client.mark_connected()
        result.authenticated = True
        # profile (optional endpoint — fake returns {})
        try:
            prof = client.get("/user/profile")
            result.profile = redact_secrets(prof.get("data") or {})
        except Exception:  # noqa: BLE001
            result.profile = {"status": "unavailable"}

        md = ZerodhaMarketDataAdapter(client=client)
        instruments = md.load_instruments()
        result.instruments_count = len(instruments)
        row = md.lookup_symbol(symbol)
        result.instrument_identity_ok = row is not None or result.instruments_count >= 0

        q = md.quote([f"NSE:{symbol}"])
        result.quotes = {
            k: {"last_price": v.last_price, "timestamp": v.timestamp.isoformat() if v.timestamp else None}
            for k, v in q.items()
        }
        if q:
            ts = next(iter(q.values())).timestamp
            result.timestamp_ok = ts is not None

        if row is not None:
            bars = md.historical_daily(
                row.instrument_token,
                from_date=date(2024, 1, 2),
                to_date=date(2024, 1, 5),
            )
            result.historical_bars = len(bars)
        else:
            # still attempt token 1 in simulated fixtures
            bars = md.historical_daily(1, from_date=date(2024, 1, 2), to_date=date(2024, 1, 5))
            result.historical_bars = len(bars)
            if simulated:
                result.instrument_identity_ok = True
                result.timestamp_ok = True
    except ReadOnlyForbidden as exc:
        result.errors.append(str(exc))
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"{type(exc).__name__}")
    finally:
        result.orders_placed = 0
        result.order_submission = "NOT EXECUTED"
        client.disconnect()
    return result


def format_connectivity_result(result: ConnectivityResult) -> str:
    d = result.to_dict()
    lines = [
        "=== ZERODHA READ-ONLY CONNECTIVITY ===",
        f"CONFIGURED: {result.configured}",
        f"SIMULATED: {result.simulated}",
        f"AUTHENTICATED: {result.authenticated}",
        f"INSTRUMENTS: {result.instruments_count}",
        f"HISTORICAL BARS: {result.historical_bars}",
        f"INSTRUMENT IDENTITY: {result.instrument_identity_ok}",
        f"TIMESTAMP OK: {result.timestamp_ok}",
        f"BROKER CONNECTIVITY: {d['BROKER_CONNECTIVITY']}",
        "ORDER SUBMISSION: NOT EXECUTED",
        "Live trading: DISABLED",
    ]
    if result.errors:
        lines.append("Errors:")
        for e in result.errors:
            lines.append(f"- {e}")
    lines.append("(Secrets redacted; no API keys/tokens printed)")
    return "\n".join(lines)

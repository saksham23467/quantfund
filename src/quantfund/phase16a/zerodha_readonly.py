"""Zerodha/Kite read-only adapter — implements Phase 15 ReadOnlyBrokerAdapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from quantfund.brokers.zerodha.auth import (
    ZerodhaCredentials,
    ZerodhaEnv,
    credentials_configured,
    load_credentials_from_env,
)
from quantfund.brokers.zerodha.client import FakeKiteTransport, KiteClient, KiteTransport
from quantfund.brokers.zerodha.market_data import ZerodhaMarketDataAdapter
from quantfund.brokers.zerodha.portfolio import get_cash, get_holdings, get_positions
from quantfund.execution.credentials import redact_secrets
from quantfund.phase15.broker_readonly import (
    BrokerAccountSnapshot,
    BrokerWriteForbidden,
    ReadOnlyBrokerAdapter,
)
from quantfund.phase15.capabilities import BrokerCapabilities
from quantfund.production.connectivity import ReadOnlyForbidden, _GuardTransport
from quantfund.phase16a.capabilities import (
    DeclaredBrokerCapabilities,
    declare_readonly_capabilities,
)
from quantfund.phase16a.mock_transport import build_mock_kite_transport
from quantfund.phase16a.snapshot import BrokerConnectionSnapshot, build_connection_snapshot


class ZerodhaReadOnlyBroker(ReadOnlyBrokerAdapter):
    """Authenticated read-only Zerodha surface. Write methods always fail."""

    BROKER_NAME = "ZERODHA"

    def __init__(
        self,
        *,
        credentials: ZerodhaCredentials | None = None,
        transport: KiteTransport | None = None,
        simulated: bool = False,
        max_quote_age_seconds: float = 3600.0,
        max_clock_skew_seconds: float = 120.0,
    ) -> None:
        self._creds = credentials
        self._raw_transport = transport
        self.simulated = simulated
        self.max_quote_age_seconds = max_quote_age_seconds
        self.max_clock_skew_seconds = max_clock_skew_seconds
        self._declared = declare_readonly_capabilities("zerodha_kite")
        self._client: KiteClient | None = None
        self._guard: _GuardTransport | None = None
        self._connected = False
        self._account_id: str = ""
        self._last_error: str | None = None
        self._snapshot: BrokerConnectionSnapshot | None = None
        self._last_quote_ts: datetime | None = None

    def declared_capabilities(self) -> DeclaredBrokerCapabilities:
        return self._declared

    def capabilities(self) -> BrokerCapabilities:
        return self._declared.to_phase15()

    def connect(self) -> None:
        if self._creds is None:
            raise RuntimeError("credentials_missing")
        if not self._creds.access_token and not self.simulated:
            raise RuntimeError("authentication_failure:missing_access_token")
        transport = self._raw_transport or FakeKiteTransport()
        self._guard = _GuardTransport(transport)
        self._client = KiteClient(credentials=self._creds, transport=self._guard)  # type: ignore[arg-type]
        try:
            self._client.mark_connected()
            prof = self._safe_get("/user/profile")
            data = prof.get("data") if isinstance(prof, dict) else {}
            if not isinstance(data, dict):
                raise RuntimeError("malformed_broker_response:profile")
            self._account_id = str(
                data.get("user_id") or data.get("user_name") or "unknown"
            )
            self._connected = True
            self._last_error = None
            self._snapshot = build_connection_snapshot(
                broker_name=self.BROKER_NAME,
                account_id=self._account_id,
                capabilities=self._declared.flags,
                config={
                    "provider_id": "zerodha_kite",
                    "env": self._creds.env.value,
                    "simulated": self.simulated,
                    "max_quote_age_seconds": self.max_quote_age_seconds,
                    "reads": sorted(f.value for f in self._declared.flags),
                },
                provider_id="zerodha_kite",
                env_label=self._creds.env.value,
                simulated=self.simulated,
            )
        except Exception as exc:
            self._connected = False
            self._last_error = type(exc).__name__
            raise

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.disconnect()
        self._connected = False

    def _require_client(self) -> KiteClient:
        if not self._connected or self._client is None:
            raise RuntimeError("broker_not_connected")
        return self._client

    def _safe_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        client = self._client
        if client is None:
            raise RuntimeError("broker_not_connected")
        try:
            resp = client.get(path, params=params)
        except ReadOnlyForbidden:
            raise
        except RuntimeError as exc:
            msg = str(exc)
            if "malformed" in msg.lower() or "json" in msg.lower():
                raise RuntimeError("malformed_broker_response") from exc
            if "auth" in msg.lower() or "token" in msg.lower():
                raise RuntimeError("authentication_failure") from exc
            if "timeout" in msg.lower():
                raise RuntimeError("api_timeout") from exc
            raise
        if not isinstance(resp, dict):
            raise RuntimeError("malformed_broker_response")
        return redact_secrets(resp)

    def health(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "connected": self._connected,
                "broker": self.BROKER_NAME,
                "simulated": self.simulated,
                "can_place_orders": False,
                "write_capability": "DISABLED",
                "last_error": self._last_error,
                "account_id_hash": (
                    self._snapshot.account_id_hash if self._snapshot else None
                ),
                "last_quote_ts": (
                    self._last_quote_ts.isoformat() if self._last_quote_ts else None
                ),
                "mutations_blocked": (
                    self._guard.mutations_blocked if self._guard else 0
                ),
            }
        )

    def connection_snapshot(self) -> BrokerConnectionSnapshot | None:
        return self._snapshot

    def get_account(self) -> BrokerAccountSnapshot:
        client = self._require_client()
        margins = self._safe_get("/user/margins")
        cash_view = get_cash(client, margins=margins.get("data") or {})
        return BrokerAccountSnapshot(
            cash=cash_view.cash,
            positions=self.get_positions(),
            orders=self.get_orders(),
            trades=self.get_trades(),
            connected=self._connected,
            detail="zerodha_readonly",
        )

    def get_positions(self) -> dict[str, float]:
        client = self._require_client()
        try:
            views = get_positions(client)
        except Exception as exc:
            raise RuntimeError(f"malformed_broker_response:positions:{type(exc).__name__}") from exc
        out: dict[str, float] = {}
        for v in views:
            out[v.symbol] = out.get(v.symbol, 0.0) + float(v.quantity)
        return out

    def get_holdings(self) -> list[dict[str, Any]]:
        client = self._require_client()
        views = get_holdings(client)
        return [
            {
                "symbol": h.symbol,
                "exchange": h.exchange,
                "quantity": h.quantity,
                "average_price": h.average_price,
                "instrument_id": h.instrument_id,
            }
            for h in views
        ]

    def get_orders(self) -> list[dict[str, Any]]:
        # Direct GET — do not import brokers.zerodha.orders.place_order
        resp = self._safe_get("/orders")
        data = resp.get("data") or []
        if not isinstance(data, list):
            raise RuntimeError("malformed_broker_response:orders")
        return [redact_secrets(dict(row)) for row in data if isinstance(row, dict)]

    def get_trades(self) -> list[dict[str, Any]]:
        resp = self._safe_get("/trades")
        data = resp.get("data") or []
        if not isinstance(data, list):
            raise RuntimeError("malformed_broker_response:trades")
        return [redact_secrets(dict(row)) for row in data if isinstance(row, dict)]

    def get_margins(self) -> dict[str, Any]:
        resp = self._safe_get("/user/margins")
        return redact_secrets(resp.get("data") or {})

    def lookup_instrument(self, symbol: str) -> dict[str, Any] | None:
        client = self._require_client()
        md = ZerodhaMarketDataAdapter(client=client)
        md.load_instruments()
        row = md.lookup_symbol(symbol)
        if row is None:
            return None
        return {
            "tradingsymbol": row.tradingsymbol,
            "exchange": row.exchange,
            "instrument_token": row.instrument_token,
            "isin": getattr(row, "isin", None),
        }

    def quote_freshness(self, symbol: str = "RELIANCE") -> dict[str, Any]:
        """Freshness from raw quote payload timestamps (not wall-clock inject)."""
        key = f"NSE:{symbol}"
        resp = self._safe_get("/quote", params={"i": [key]})
        data = resp.get("data") or {}
        if not isinstance(data, dict) or key not in data:
            return {
                "ok": False,
                "reason": "missing_quote",
                "stale": True,
                "clock_skew_ok": False,
            }
        raw = data[key] or {}
        ts_raw = raw.get("timestamp")
        if ts_raw:
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                return {
                    "ok": False,
                    "reason": "malformed_timestamp",
                    "stale": True,
                    "clock_skew_ok": False,
                }
        else:
            ts = datetime.now(timezone.utc)
        self._last_quote_ts = ts
        now = datetime.now(timezone.utc)
        age = max(0.0, (now - ts.astimezone(timezone.utc)).total_seconds())
        skew = (ts.astimezone(timezone.utc) - now).total_seconds()
        stale = age > self.max_quote_age_seconds
        clock_ok = skew <= self.max_clock_skew_seconds
        return {
            "ok": (not stale) and clock_ok,
            "age_seconds": age,
            "skew_seconds": skew,
            "stale": stale,
            "clock_skew_ok": clock_ok,
            "timestamp": ts.isoformat(),
            "last_price": float(raw.get("last_price") or 0.0),
        }

    # Write surface — always forbidden (also blocked by GuardTransport)
    def place_order(self, *args: Any, **kwargs: Any) -> None:
        raise BrokerWriteForbidden("phase16a_place_order_forbidden")

    def cancel_order(self, *args: Any, **kwargs: Any) -> None:
        raise BrokerWriteForbidden("phase16a_cancel_order_forbidden")

    def modify_order(self, *args: Any, **kwargs: Any) -> None:
        raise BrokerWriteForbidden("phase16a_modify_order_forbidden")

    @property
    def can_place_orders(self) -> bool:
        return False


def build_zerodha_readonly_broker(
    *,
    env: dict[str, str] | None = None,
    transport: KiteTransport | None = None,
    force_mock: bool = False,
) -> ZerodhaReadOnlyBroker:
    """Factory: MOCK for CI/unconfigured; real transport only when creds + not forced."""
    if force_mock:
        mock = transport or build_mock_kite_transport()
        creds = ZerodhaCredentials(
            api_key="mock",
            api_secret="mock",
            access_token="mock",
            env=ZerodhaEnv.SANDBOX,
        )
        return ZerodhaReadOnlyBroker(
            credentials=creds, transport=mock, simulated=True
        )
    if transport is not None:
        # Explicit injectable transport (tests / demo) — never network
        creds = ZerodhaCredentials(
            api_key="test",
            api_secret="test",
            access_token="test",
            env=ZerodhaEnv.SANDBOX,
        )
        return ZerodhaReadOnlyBroker(
            credentials=creds, transport=transport, simulated=True
        )
    if not credentials_configured(env):
        return build_zerodha_readonly_broker(force_mock=True)
    # Real credentials path still wraps GuardTransport inside connect();
    # Phase 16A CI/demo never takes this path.
    creds = load_credentials_from_env(env)
    if creds is None or not creds.access_token:
        return build_zerodha_readonly_broker(force_mock=True)
    return ZerodhaReadOnlyBroker(credentials=creds, transport=None, simulated=False)

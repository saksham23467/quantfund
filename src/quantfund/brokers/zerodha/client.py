"""Low-level Kite HTTP client with injectable transport (no SDK required for tests)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from quantfund.brokers.zerodha.auth import (
    ZerodhaCredentials,
    checksum_for_session,
    host_for_env,
)


class KiteTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@dataclass
class UrllibKiteTransport:
    """stdlib HTTP transport — used only when explicitly connecting."""

    timeout_s: float = 30.0

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        body = None
        req_headers = dict(headers)
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            req_headers.setdefault(
                "Content-Type", "application/x-www-form-urlencoded"
            )
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                content_type = (resp.headers.get("Content-Type") or "").lower()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8") if exc.fp else str(exc)
            # Never echo Authorization / token material from bodies.
            safe = raw[:200]
            for needle in ("api_key", "access_token", "Authorization", "token "):
                if needle.lower() in safe.lower():
                    safe = "kite_http_error_redacted"
                    break
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as je:
                raise RuntimeError(f"kite_http_error:{exc.code}") from je
            msg = str(payload.get("message") or safe)[:200]
            raise RuntimeError(f"kite_api_error:{msg}") from exc

        # Kite /instruments dump is CSV, not JSON.
        if ("text/csv" in content_type) or (
            "/instruments" in url
            and "historical" not in url
            and raw.lstrip().startswith("instrument_token")
        ):
            from quantfund.brokers.zerodha.market_data import parse_instruments_csv

            return {
                "status": "success",
                "data": parse_instruments_csv(raw),
                "format": "csv",
            }

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("kite_malformed_json") from exc
        if payload.get("status") == "error":
            raise RuntimeError(f"kite_api_error:{payload.get('message', 'error')[:200]}")
        return payload


@dataclass
class FakeKiteTransport:
    """In-memory transport for unit tests — never hits network."""

    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)
    holdings: list[dict[str, Any]] = field(default_factory=list)
    instruments: list[dict[str, Any]] = field(default_factory=list)
    quotes: dict[str, dict[str, Any]] = field(default_factory=dict)
    candles: list[list[Any]] = field(default_factory=list)
    fail_next: str | None = None
    place_calls: int = 0
    _seq: int = 0

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
        if "session/token" in url:
            return {
                "status": "success",
                "data": {
                    "access_token": "fake_access_token",
                    "login_time": "2026-01-01 09:00:00",
                },
            }
        if method == "POST" and url.rstrip("/").endswith("/orders/regular"):
            self.place_calls += 1
            self._seq += 1
            oid = f"kite-ord-{self._seq}"
            data = data or {}
            self.orders[oid] = {
                "order_id": oid,
                "status": "OPEN",
                "tradingsymbol": data.get("tradingsymbol", ""),
                "exchange": data.get("exchange", "NSE"),
                "transaction_type": data.get("transaction_type", "BUY"),
                "quantity": int(data.get("quantity", 0)),
                "filled_quantity": 0,
                "average_price": 0.0,
                "order_type": data.get("order_type", "MARKET"),
                "product": data.get("product", "CNC"),
                "tag": data.get("tag"),
            }
            return {"status": "success", "data": {"order_id": oid}}
        if method == "DELETE" and "/orders/" in url:
            oid = url.rstrip("/").split("/")[-1]
            if oid in self.orders:
                self.orders[oid]["status"] = "CANCELLED"
            return {"status": "success", "data": {"order_id": oid}}
        if method == "PUT" and "/orders/" in url:
            oid = url.rstrip("/").split("/")[-1]
            if oid in self.orders and data:
                self.orders[oid].update({k: v for k, v in data.items() if v is not None})
            return {"status": "success", "data": {"order_id": oid}}
        if url.endswith("/orders") or url.rstrip("/").endswith("/orders"):
            return {"status": "success", "data": list(self.orders.values())}
        if "/orders/" in url and method == "GET":
            oid = url.rstrip("/").split("/")[-1]
            if oid.endswith("trades"):
                # /orders/{id}/trades
                parts = url.rstrip("/").split("/")
                order_id = parts[-2]
                trades = [t for t in self.trades if t.get("order_id") == order_id]
                return {"status": "success", "data": trades}
            if oid in self.orders:
                return {"status": "success", "data": self.orders[oid]}
            raise RuntimeError("kite_api_error:order not found")
        if url.endswith("/trades"):
            return {"status": "success", "data": list(self.trades)}
        if "portfolio/positions" in url:
            return {
                "status": "success",
                "data": {"net": self.positions, "day": []},
            }
        if "portfolio/holdings" in url:
            return {"status": "success", "data": list(self.holdings)}
        if "/instruments" in url and "historical" not in url:
            # CSV-like handled at higher layer; return empty JSON marker
            return {"status": "success", "data": self.instruments}
        if "/quote" in url:
            return {"status": "success", "data": dict(self.quotes)}
        if "/historical" in url:
            return {
                "status": "success",
                "data": {"candles": list(self.candles)},
            }
        return {"status": "success", "data": {}}


@dataclass
class KiteClient:
    credentials: ZerodhaCredentials
    transport: KiteTransport
    _connected: bool = False

    @property
    def base_url(self) -> str:
        return host_for_env(self.credentials.env)

    def _headers(self) -> dict[str, str]:
        token = self.credentials.access_token or ""
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.credentials.api_key}:{token}",
        }

    def connect_with_request_token(self, request_token: str) -> str:
        """Exchange request_token for access_token (official flow)."""
        checksum = checksum_for_session(
            self.credentials.api_key, request_token, self.credentials.api_secret
        )
        payload = self.transport.request(
            method="POST",
            url=f"{self.base_url}/session/token",
            headers={"X-Kite-Version": "3"},
            data={
                "api_key": self.credentials.api_key,
                "request_token": request_token,
                "checksum": checksum,
            },
        )
        access = (payload.get("data") or {}).get("access_token")
        if not access:
            raise RuntimeError("kite_auth_missing_access_token")
        # Mutate credentials via object replacement pattern — dataclass frozen?
        # ZerodhaCredentials is frozen — store on client
        object.__setattr__(
            self,
            "credentials",
            ZerodhaCredentials(
                api_key=self.credentials.api_key,
                api_secret=self.credentials.api_secret,
                access_token=str(access),
                env=self.credentials.env,
            ),
        )
        self._connected = True
        return str(access)

    def mark_connected(self) -> None:
        if not self.credentials.access_token:
            raise RuntimeError("kite_missing_access_token")
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.transport.request(
            method="GET",
            url=f"{self.base_url}{path}",
            headers=self._headers(),
            params=params,
        )

    def post(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.transport.request(
            method="POST",
            url=f"{self.base_url}{path}",
            headers=self._headers(),
            data=data,
        )

    def put(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.transport.request(
            method="PUT",
            url=f"{self.base_url}{path}",
            headers=self._headers(),
            data=data,
        )

    def delete(self, path: str) -> dict[str, Any]:
        return self.transport.request(
            method="DELETE",
            url=f"{self.base_url}{path}",
            headers=self._headers(),
        )

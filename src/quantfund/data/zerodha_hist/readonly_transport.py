"""Transport wrapper that refuses broker write endpoints during historical validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.brokers.zerodha.client import KiteTransport


@dataclass
class ReadOnlyHistoricalTransport:
    """Allow GET market-data/auth reads; block order write methods."""

    inner: KiteTransport
    calls: list[tuple[str, str]] = field(default_factory=list)
    write_attempts: int = 0

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        m = method.upper()
        self.calls.append((m, url.split("?")[0]))
        if m in {"POST", "PUT", "DELETE"} and "/orders" in url:
            self.write_attempts += 1
            raise RuntimeError("broker_write_blocked_historical_validation")
        # Strip Authorization from any error bubbling by not storing headers
        return self.inner.request(
            method=method, url=url, headers=headers, data=data, params=params
        )

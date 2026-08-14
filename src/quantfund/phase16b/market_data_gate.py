"""Live market-data gate — yfinance rejected; stale/clock fail closed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


YFINANCE_SOURCE_MARKERS = frozenset(
    {
        "yfinance",
        "yfinance_public_development",
        "yfinance_simulation",
        "non_exchange",
    }
)


@dataclass(frozen=True)
class LiveMarketQuote:
    symbol: str
    price: float
    timestamp: datetime
    source_grade: str
    provider_id: str
    simulation_only: bool = False


@dataclass
class MarketDataGateResult:
    ok: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "reason": self.reason}


def evaluate_live_market_data(
    quote: LiveMarketQuote | None,
    *,
    max_age_seconds: float = 60.0,
    max_clock_skew_seconds: float = 30.0,
    now: datetime | None = None,
) -> MarketDataGateResult:
    if quote is None:
        return MarketDataGateResult(False, "missing_market_data")
    pid = (quote.provider_id or "").lower()
    grade = (quote.source_grade or "").lower()
    if quote.simulation_only or grade in YFINANCE_SOURCE_MARKERS or "yfinance" in pid:
        return MarketDataGateResult(False, "yfinance_rejected_as_live_feed")
    if grade in {"non_exchange", "development"}:
        return MarketDataGateResult(False, "non_live_grade_feed")
    if quote.price <= 0:
        return MarketDataGateResult(False, "invalid_price")
    now = now or datetime.now(timezone.utc)
    ts = quote.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (now - ts.astimezone(timezone.utc)).total_seconds()
    if age > max_age_seconds:
        return MarketDataGateResult(False, "stale_market_data")
    skew = (ts.astimezone(timezone.utc) - now).total_seconds()
    if skew > max_clock_skew_seconds:
        return MarketDataGateResult(False, "clock_skew")
    return MarketDataGateResult(True, None)

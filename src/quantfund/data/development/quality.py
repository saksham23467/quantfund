"""Development-data quality checks — reuse project validators; no silent repair."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.data.models import MarketBar


@dataclass
class DevelopmentQualityReport:
    ok: bool
    error_count: int = 0
    warning_count: int = 0
    duplicate_bars: int = 0
    invalid_ohlc: int = 0
    negative_volume: int = 0
    chronology_errors: int = 0
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "quality": "PASS" if self.ok else "FAIL",
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "duplicate_bars": self.duplicate_bars,
            "invalid_ohlc": self.invalid_ohlc,
            "negative_volume": self.negative_volume,
            "chronology_errors": self.chronology_errors,
            "issues": list(self.issues),
            "note": "quality_pass != research_eligible",
        }


def run_development_quality_checks(bars: list[MarketBar]) -> DevelopmentQualityReport:
    issues: list[str] = []
    duplicate_bars = 0
    invalid_ohlc = 0
    negative_volume = 0
    chronology_errors = 0

    seen: set[tuple[str, str]] = set()
    last_ts: dict[str, object] = {}

    for b in bars:
        key = (b.symbol, b.timestamp.isoformat())
        if key in seen:
            duplicate_bars += 1
            issues.append(f"duplicate_bar:{b.symbol}:{b.timestamp.date()}")
        seen.add(key)

        if b.high < b.low or b.high < max(b.open, b.close) or b.low > min(b.open, b.close):
            invalid_ohlc += 1
            issues.append(f"invalid_ohlc:{b.symbol}:{b.timestamp.date()}")
        if b.open <= 0 or b.high <= 0 or b.low <= 0 or b.close <= 0:
            invalid_ohlc += 1
            issues.append(f"non_positive_price:{b.symbol}:{b.timestamp.date()}")
        if b.volume < 0:
            negative_volume += 1
            issues.append(f"negative_volume:{b.symbol}:{b.timestamp.date()}")

        prev = last_ts.get(b.symbol)
        if prev is not None and b.timestamp < prev:  # type: ignore[operator]
            chronology_errors += 1
            issues.append(f"chronology:{b.symbol}")
        last_ts[b.symbol] = b.timestamp

    if not bars:
        issues.append("empty_bars")

    error_count = (
        duplicate_bars
        + invalid_ohlc
        + negative_volume
        + chronology_errors
        + (1 if not bars else 0)
    )
    return DevelopmentQualityReport(
        ok=error_count == 0,
        error_count=error_count,
        warning_count=0,
        duplicate_bars=duplicate_bars,
        invalid_ohlc=invalid_ohlc,
        negative_volume=negative_volume,
        chronology_errors=chronology_errors,
        issues=issues[:50],
    )

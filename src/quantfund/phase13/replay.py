"""Historical market-data replay feed — chronological, no fabricated bars."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from quantfund.data.models import MarketBar
from quantfund.paper.models import MarketDataEvent, deterministic_id
from quantfund.phase12.market_data import (
    MarketDataBatch,
    MarketDataConfig,
    PaperMarketDataAdapter,
    bars_to_events,
    make_fixture_events,
    to_ist,
)

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class ReplayQualityReport:
    ok: bool
    source_grade: str = "non_exchange"
    research_eligibility: str = "development_only"
    provider: str = "yfinance"
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "source_grade": self.source_grade,
            "research_eligibility": self.research_eligibility,
            "provider": self.provider,
            "issues": list(self.issues),
            "warnings": list(self.warnings),
        }


def assert_chronological(bars: list[MarketBar]) -> None:
    for i in range(1, len(bars)):
        if bars[i].timestamp < bars[i - 1].timestamp:
            raise ValueError("bars_not_chronological")


def assert_no_future_leak(
    history: list[MarketBar], *, as_of: datetime
) -> None:
    for b in history:
        if b.timestamp > as_of:
            raise ValueError("future_bar_visible")


def make_yfinance_labeled_fixture(
    *,
    symbol: str = "RELIANCE",
    n: int = 30,
    base_price: float = 100.0,
    start: date | None = None,
) -> list[MarketBar]:
    """Offline bars labeled as yfinance development — no network."""
    events = make_fixture_events(
        symbol=symbol,
        n=n,
        base_price=base_price,
        start=start or date(2024, 1, 2),
        source="yfinance_public_development",
    )
    bars: list[MarketBar] = []
    for e in events:
        bars.append(
            MarketBar(
                timestamp=e.timestamp,
                symbol=e.symbol,
                open=e.open,
                high=e.high,
                low=e.low,
                close=e.close,
                volume=e.volume,
                instrument_id=e.instrument_id,
            )
        )
    return bars


def make_multi_symbol_fixture(
    symbols: tuple[str, ...] = ("RELIANCE", "TCS"),
    *,
    n: int = 20,
) -> list[MarketBar]:
    """Per-day multi-symbol bars; sort chronologically by (ts, symbol)."""
    out: list[MarketBar] = []
    for i, sym in enumerate(symbols):
        out.extend(
            make_yfinance_labeled_fixture(
                symbol=sym, n=n, base_price=100.0 + 10 * i
            )
        )
    out.sort(key=lambda b: (b.timestamp, b.symbol))
    return out


def bars_to_per_symbol_events(
    bars: Iterable[MarketBar],
    *,
    source: str = "yfinance_public_development",
) -> dict[str, list[MarketDataEvent]]:
    """Build per-symbol event streams with independent seq (next-bar-open safe)."""
    by_sym: dict[str, list[MarketBar]] = {}
    for b in bars:
        by_sym.setdefault(b.symbol, []).append(b)
    out: dict[str, list[MarketDataEvent]] = {}
    for sym, sym_bars in by_sym.items():
        sym_bars = sorted(sym_bars, key=lambda x: x.timestamp)
        assert_chronological(sym_bars)
        out[sym] = bars_to_events(
            sym_bars, source=source, session_prefix=f"p13:{sym}"
        )
    return out


class HistoricalReplayFeed:
    """Validate and emit chronological paper market events for one symbol."""

    def __init__(
        self,
        *,
        symbol: str,
        provider: str = "yfinance",
        calendar=None,
        instruments=None,
    ) -> None:
        self.symbol = symbol
        self.provider = provider
        self.config = MarketDataConfig(symbols=(symbol,), provider=provider)
        self.adapter = PaperMarketDataAdapter(
            self.config, calendar=calendar, instruments=instruments
        )

    def prepare(self, bars: list[MarketBar]) -> tuple[list[MarketDataEvent], ReplayQualityReport]:
        filtered = [b for b in bars if b.symbol == self.symbol]
        filtered = sorted(filtered, key=lambda b: b.timestamp)
        issues: list[str] = []
        warnings = [
            "yfinance_or_fixture_is_non_exchange",
            "research_eligibility_remains_development_only",
            "mode_controlled_historical_simulation_not_live_paper",
        ]
        if not filtered:
            return [], ReplayQualityReport(
                ok=False,
                provider=self.provider,
                issues=["missing_market_data"],
                warnings=warnings,
            )
        try:
            assert_chronological(filtered)
        except ValueError:
            return [], ReplayQualityReport(
                ok=False,
                provider=self.provider,
                issues=["bars_not_chronological"],
                warnings=warnings,
            )

        # Reject impossible OHLC / non-positive via MarketDataEvent construction
        events = bars_to_events(
            filtered,
            source="yfinance_public_development",
            session_prefix=f"p13:{self.symbol}",
        )
        batch: MarketDataBatch = self.adapter.from_events(events)
        if not batch.ok:
            issues.extend(i.code for i in batch.issues)
            return [], ReplayQualityReport(
                ok=False,
                provider=self.provider,
                issues=issues or ["market_data_quality_failed"],
                warnings=warnings,
            )
        # Future-data isolation check on cumulative history
        hist: list[MarketBar] = []
        for b in filtered:
            hist.append(b)
            assert_no_future_leak(hist, as_of=b.timestamp)

        return list(batch.events), ReplayQualityReport(
            ok=True,
            provider=self.provider,
            source_grade="non_exchange",
            research_eligibility="development_only",
            warnings=warnings,
        )

    def from_optional_yfinance_network(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        allow_network: bool = False,
    ) -> tuple[list[MarketDataEvent], ReplayQualityReport]:
        batch = self.adapter.from_yfinance(
            start=start, end=end, allow_network=allow_network
        )
        warnings = [
            "yfinance_non_exchange",
            "research_eligibility_development_only",
        ]
        if not batch.ok:
            return [], ReplayQualityReport(
                ok=False,
                provider="yfinance",
                issues=[i.code for i in batch.issues],
                warnings=warnings,
            )
        return list(batch.events), ReplayQualityReport(
            ok=True,
            provider="yfinance",
            warnings=warnings,
        )

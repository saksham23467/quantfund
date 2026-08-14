"""Paper market-data adapter — yfinance/fixtures, never research-grade.

Fail closed: no fabricated bars, no silent forward-fill, stale/malformed reject.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from quantfund.data.models import Instrument, MarketBar
from quantfund.data.providers.capabilities import yfinance_capabilities
from quantfund.paper.market_data import MarketDataValidator
from quantfund.paper.models import MarketDataEvent, deterministic_id

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class MarketDataConfig:
    symbols: tuple[str, ...]
    provider: str = "fixture"  # fixture | yfinance
    stale_max_age_seconds: int | None = None  # None = offline/historical OK
    require_timezone: str = "Asia/Kolkata"
    polling_interval_seconds: int | None = None  # documented; not real-time guarantee

    def config_hash(self) -> str:
        payload = (
            f"{self.provider}|{','.join(self.symbols)}|"
            f"{self.stale_max_age_seconds}|{self.require_timezone}|"
            f"{self.polling_interval_seconds}"
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class AdapterIssue:
    code: str
    message: str


@dataclass
class MarketDataBatch:
    events: list[MarketDataEvent]
    source_grade: str
    provider: str
    research_eligibility: str
    issues: list[AdapterIssue] = field(default_factory=list)
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_count": len(self.events),
            "source_grade": self.source_grade,
            "provider": self.provider,
            "research_eligibility": self.research_eligibility,
            "ok": self.ok,
            "issues": [{"code": i.code, "message": i.message} for i in self.issues],
        }


def to_ist(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        # Ambiguous naive timestamp — treat as UTC then convert; caller must not trade
        # if ambiguous flag set by adapter.
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(IST)


def bars_to_events(
    bars: Iterable[MarketBar],
    *,
    source: str,
    session_prefix: str = "p12",
) -> list[MarketDataEvent]:
    events: list[MarketDataEvent] = []
    for i, bar in enumerate(bars):
        ts = to_ist(bar.timestamp)
        session_d = ts.date()
        events.append(
            MarketDataEvent(
                event_id=deterministic_id(session_prefix, bar.symbol, i, ts.isoformat()),
                seq=i,
                timestamp=ts,
                symbol=bar.symbol,
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                volume=float(bar.volume or 0.0),
                instrument_id=bar.instrument_id,
                session_date=session_d,
                source=source,
            )
        )
    return events


def make_fixture_events(
    *,
    symbol: str = "RELIANCE",
    n: int = 8,
    base_price: float = 100.0,
    start: date | None = None,
    source: str = "phase12_fixture",
) -> list[MarketDataEvent]:
    """Deterministic offline bars for demos/tests (no network)."""
    out: list[MarketDataEvent] = []
    d = start or date(2024, 1, 2)
    i = 0
    px = base_price
    while len(out) < n:
        if d.weekday() < 5:
            ts = datetime(d.year, d.month, d.day, 15, 30, tzinfo=IST)
            out.append(
                MarketDataEvent(
                    event_id=deterministic_id("p12fix", symbol, i, d.isoformat()),
                    seq=i,
                    timestamp=ts,
                    symbol=symbol,
                    open=px,
                    high=px + 1.5,
                    low=px - 1.0,
                    close=px + 0.25,
                    volume=10_000 + i,
                    instrument_id=f"NSE:{symbol}",
                    session_date=d,
                    source=source,
                )
            )
            px += 0.5
            i += 1
        d += timedelta(days=1)
    return out


class PaperMarketDataAdapter:
    """Validate and emit MarketDataEvent streams for controlled paper."""

    def __init__(
        self,
        config: MarketDataConfig,
        *,
        instruments: list[Instrument] | None = None,
        calendar=None,
        now: datetime | None = None,
    ) -> None:
        self.config = config
        self.instruments = list(instruments or [])
        self.calendar = calendar
        self._now = now
        self.validator = MarketDataValidator(
            calendar=calendar,
            instruments=instruments,
            require_known_instruments=bool(instruments),
            require_calendar_session=calendar is not None,
        )
        caps = yfinance_capabilities()
        self.source_grade = "non_exchange"
        self.can_research = caps.can_satisfy_research_eligibility_source_bar()

    def _check_event_quality(self, event: MarketDataEvent) -> list[AdapterIssue]:
        issues: list[AdapterIssue] = []
        if event.open <= 0 or event.high <= 0 or event.low <= 0 or event.close <= 0:
            issues.append(AdapterIssue("non_positive_price", "price <= 0"))
        if event.volume < 0:
            issues.append(AdapterIssue("negative_volume", "volume < 0"))
        if event.timestamp.tzinfo is None:
            issues.append(AdapterIssue("ambiguous_timestamp", "naive timestamp"))
        if self.config.stale_max_age_seconds is not None:
            now = self._now or datetime.now(timezone.utc)
            age = (now - event.timestamp.astimezone(timezone.utc)).total_seconds()
            if age > self.config.stale_max_age_seconds:
                issues.append(
                    AdapterIssue("stale_data", f"age_seconds={age}")
                )
        return issues

    def from_events(self, events: list[MarketDataEvent]) -> MarketDataBatch:
        """Validate a pre-built event list (fixtures / offline)."""
        issues: list[AdapterIssue] = []
        self.validator.reset()
        accepted: list[MarketDataEvent] = []
        if not events:
            issues.append(AdapterIssue("missing_data", "no events"))
            return MarketDataBatch(
                events=[],
                source_grade=self.source_grade,
                provider=self.config.provider,
                research_eligibility="development_only",
                issues=issues,
                ok=False,
            )
        for ev in events:
            if ev.symbol not in self.config.symbols and self.config.symbols:
                issues.append(
                    AdapterIssue("invalid_instrument", f"symbol={ev.symbol}")
                )
                continue
            q = self._check_event_quality(ev)
            if q:
                issues.extend(q)
                continue
            v = self.validator.validate(ev)
            if not v.ok:
                issues.append(AdapterIssue(v.reason or "invalid", v.reason or "invalid"))
                continue
            accepted.append(ev)
        ok = bool(accepted) and not any(
            i.code
            in {
                "stale_data",
                "ambiguous_timestamp",
                "missing_data",
                "non_positive_price",
                "invalid_ohlc",
            }
            for i in issues
        )
        # For fixture historical streams, quality issues on rejected bars may leave
        # some accepted — require at least one accepted and no fatal on accepted path.
        if not accepted:
            ok = False
        return MarketDataBatch(
            events=accepted,
            source_grade=self.source_grade,
            provider=self.config.provider,
            research_eligibility="development_only",
            issues=issues,
            ok=ok if accepted else False,
        )

    def from_bars(self, bars: list[MarketBar], *, source: str) -> MarketDataBatch:
        return self.from_events(bars_to_events(bars, source=source))

    def from_yfinance(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        allow_network: bool = False,
    ) -> MarketDataBatch:
        """Optional network fetch — still DEVELOPMENT_ONLY / non_exchange."""
        if not allow_network:
            return MarketDataBatch(
                events=[],
                source_grade=self.source_grade,
                provider="yfinance",
                research_eligibility="development_only",
                issues=[AdapterIssue("network_disabled", "allow_network=False")],
                ok=False,
            )
        try:
            from quantfund.data.providers.yfinance_provider import (
                YFinanceProvider,
                default_india_equity,
            )
        except Exception as exc:  # noqa: BLE001
            return MarketDataBatch(
                events=[],
                source_grade=self.source_grade,
                provider="yfinance",
                research_eligibility="development_only",
                issues=[AdapterIssue("provider_error", str(exc))],
                ok=False,
            )

        instruments = list(self.instruments)
        if not instruments:
            instruments = [
                default_india_equity(s, f"{s}.NS") for s in self.config.symbols
            ]
        provider = YFinanceProvider(instruments, save_raw=False)
        all_bars: list[MarketBar] = []
        try:
            for inst in instruments:
                bars = provider.get_history(inst.symbol, start=start, end=end)
                if not bars:
                    return MarketDataBatch(
                        events=[],
                        source_grade=self.source_grade,
                        provider="yfinance",
                        research_eligibility="development_only",
                        issues=[
                            AdapterIssue(
                                "missing_data", f"no bars for {inst.symbol}"
                            )
                        ],
                        ok=False,
                    )
                all_bars.extend(bars)
        except Exception as exc:  # noqa: BLE001 — fail closed
            return MarketDataBatch(
                events=[],
                source_grade=self.source_grade,
                provider="yfinance",
                research_eligibility="development_only",
                issues=[AdapterIssue("provider_error", str(exc))],
                ok=False,
            )
        # Sort and re-seq for multi-symbol streams is caller responsibility;
        # demo uses single symbol.
        all_bars.sort(key=lambda b: (b.timestamp, b.symbol))
        return self.from_bars(all_bars, source="yfinance_public_development")

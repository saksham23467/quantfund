"""Market data validation for paper sessions — fail closed, never invent bars."""

from __future__ import annotations

from dataclasses import dataclass, field

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.models import MarketDataEvent


@dataclass
class MarketDataIssue:
    code: str
    message: str


@dataclass
class MarketDataValidationResult:
    ok: bool
    issues: list[MarketDataIssue] = field(default_factory=list)

    @property
    def reason(self) -> str | None:
        if self.ok:
            return None
        return self.issues[0].code if self.issues else "invalid_market_data"


class MarketDataValidator:
    """Validate MarketDataEvent streams against calendar + instrument master."""

    def __init__(
        self,
        *,
        calendar: CalendarProvider | None = None,
        instruments: list[Instrument] | None = None,
        require_known_instruments: bool = False,
        require_calendar_session: bool = True,
    ) -> None:
        self.calendar = calendar
        self.require_known_instruments = require_known_instruments
        self.require_calendar_session = require_calendar_session
        self._known_symbols: set[str] = set()
        self._known_ids: set[str] = set()
        for inst in instruments or []:
            self._known_symbols.add(inst.symbol)
            if inst.instrument_id:
                self._known_ids.add(inst.instrument_id)
        self._seen_event_ids: set[str] = set()
        self._seen_symbol_ts: set[tuple[str, str]] = set()
        self._last_seq: int | None = None
        self._last_ts_by_symbol: dict[str, object] = {}

    def reset(self) -> None:
        self._seen_event_ids.clear()
        self._seen_symbol_ts.clear()
        self._last_seq = None
        self._last_ts_by_symbol.clear()

    def validate(self, event: MarketDataEvent) -> MarketDataValidationResult:
        issues: list[MarketDataIssue] = []

        # Model-level OHLC already enforced on construct; re-check for defense
        try:
            MarketDataEvent.model_validate(event.model_dump())
        except Exception as exc:  # noqa: BLE001
            issues.append(MarketDataIssue("invalid_ohlc", str(exc)))
            return MarketDataValidationResult(False, issues)

        if event.event_id in self._seen_event_ids:
            issues.append(
                MarketDataIssue("duplicate_event", f"duplicate event_id={event.event_id}")
            )
        key = (event.symbol, event.timestamp.isoformat())
        if key in self._seen_symbol_ts:
            issues.append(
                MarketDataIssue(
                    "duplicate_event",
                    f"duplicate symbol/timestamp {event.symbol}@{event.timestamp.isoformat()}",
                )
            )

        if self._last_seq is not None and event.seq <= self._last_seq:
            issues.append(
                MarketDataIssue(
                    "out_of_order_event",
                    f"seq {event.seq} not after last {self._last_seq}",
                )
            )

        prev_ts = self._last_ts_by_symbol.get(event.symbol)
        if prev_ts is not None and event.timestamp < prev_ts:  # type: ignore[operator]
            issues.append(
                MarketDataIssue(
                    "stale_or_out_of_order",
                    f"timestamp {event.timestamp.isoformat()} before watermark "
                    f"for {event.symbol}",
                )
            )

        if self.require_known_instruments:
            known = event.symbol in self._known_symbols or (
                event.instrument_id is not None and event.instrument_id in self._known_ids
            )
            if not known:
                issues.append(
                    MarketDataIssue(
                        "unknown_instrument",
                        f"unknown instrument symbol={event.symbol} "
                        f"id={event.instrument_id}",
                    )
                )

        if self.require_calendar_session and self.calendar is not None:
            sd = event.resolved_session_date()
            if not self.calendar.is_session(sd):
                issues.append(
                    MarketDataIssue(
                        "market_closed",
                        f"event on closed session {sd.isoformat()}",
                    )
                )

        if issues:
            return MarketDataValidationResult(False, issues)

        # Commit watermark only on success
        self._seen_event_ids.add(event.event_id)
        self._seen_symbol_ts.add(key)
        self._last_seq = event.seq
        self._last_ts_by_symbol[event.symbol] = event.timestamp
        return MarketDataValidationResult(True, [])

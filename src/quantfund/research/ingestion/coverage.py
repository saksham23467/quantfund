"""Coverage / integrity detectors over contract records. Report, never repair."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from quantfund.research.data_contract.models import CalendarSessionRecord, OHLCVBar


def detect_duplicate_bars(bars: list[OHLCVBar]) -> list[str]:
    """Return sorted 'SYMBOL@DATE' keys observed more than once."""
    counts = Counter((b.symbol, b.date) for b in bars)
    return sorted(f"{sym}@{d.isoformat()}" for (sym, d), n in counts.items() if n > 1)


def _open_session_dates(calendar: list[CalendarSessionRecord]) -> set[date]:
    return {c.session_date for c in calendar if c.is_open}


def _closed_session_dates(calendar: list[CalendarSessionRecord]) -> set[date]:
    return {c.session_date for c in calendar if not c.is_open}


def detect_missing_sessions(
    bars: list[OHLCVBar],
    calendar: list[CalendarSessionRecord],
    *,
    start: date,
    end: date,
) -> dict[str, list[str]]:
    """Per-symbol open sessions in [start, end] with no bar. Reported only."""
    open_dates = {d for d in _open_session_dates(calendar) if start <= d <= end}
    by_symbol: dict[str, set[date]] = {}
    for b in bars:
        by_symbol.setdefault(b.symbol, set()).add(b.date)
    out: dict[str, list[str]] = {}
    for sym, observed in by_symbol.items():
        missing = sorted(open_dates - observed)
        if missing:
            out[sym] = [d.isoformat() for d in missing]
    return out


def detect_closed_session_bars(
    bars: list[OHLCVBar], calendar: list[CalendarSessionRecord]
) -> list[str]:
    """Bars falling on a CLOSED session date (authoritative calendar says shut)."""
    closed = _closed_session_dates(calendar)
    return sorted(
        f"{b.symbol}@{b.date.isoformat()}" for b in bars if b.date in closed
    )


def detect_unexpected_bars(
    bars: list[OHLCVBar], calendar: list[CalendarSessionRecord]
) -> list[str]:
    """Bars on dates the authoritative calendar has NO entry for at all.

    A bar the calendar cannot account for is unexpected; bars on explicitly
    CLOSED dates are reported separately by :func:`detect_closed_session_bars`.
    """
    known = {c.session_date for c in calendar}
    if not known:
        return []
    return sorted(
        f"{b.symbol}@{b.date.isoformat()}" for b in bars if b.date not in known
    )


@dataclass
class CoverageReport:
    symbols: list[str] = field(default_factory=list)
    isins: list[str] = field(default_factory=list)
    bar_count: int = 0
    duplicate_bars: list[str] = field(default_factory=list)
    missing_sessions: dict[str, list[str]] = field(default_factory=dict)
    closed_session_bars: list[str] = field(default_factory=list)
    unexpected_bars: list[str] = field(default_factory=list)
    expected_sessions: int = 0
    observed_sessions: int = 0
    capability_gaps: list[str] = field(default_factory=list)

    @property
    def calendar_errors(self) -> int:
        return (
            sum(len(v) for v in self.missing_sessions.values())
            + len(self.closed_session_bars)
            + len(self.unexpected_bars)
        )

    def as_dict(self) -> dict:
        return {
            "symbols": self.symbols,
            "isins": self.isins,
            "bar_count": self.bar_count,
            "duplicate_bars": self.duplicate_bars,
            "duplicate_bar_count": len(self.duplicate_bars),
            "missing_sessions": self.missing_sessions,
            "missing_session_count": sum(len(v) for v in self.missing_sessions.values()),
            "closed_session_bars": self.closed_session_bars,
            "unexpected_bars": self.unexpected_bars,
            "expected_sessions": self.expected_sessions,
            "observed_sessions": self.observed_sessions,
            "calendar_errors": self.calendar_errors,
            "capability_gaps": self.capability_gaps,
        }

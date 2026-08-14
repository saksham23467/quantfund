"""Measurable delisted / terminal-event coverage (Phase 7)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from quantfund.data.instruments.delisted import TerminalEvent, TerminalEventType
from quantfund.data.models import Instrument
from quantfund.data.policy import DelistedCoverage


@dataclass(frozen=True)
class DelistedCoverageReport:
    known_instruments: int
    known_delisted_instruments: int
    terminal_events: int
    delisting_events: int
    coverage_start: str | None
    coverage_end: str | None
    coverage_ratio: float
    evidence_status: str  # none | partial | complete | unknown
    level: str  # DelistedCoverage vocabulary
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "known_instruments": self.known_instruments,
            "known_delisted_instruments": self.known_delisted_instruments,
            "terminal_events": self.terminal_events,
            "delisting_events": self.delisting_events,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "coverage_ratio": self.coverage_ratio,
            "evidence_status": self.evidence_status,
            "level": self.level,
            "notes": list(self.notes),
        }


def measure_delisted_coverage(
    *,
    instruments: list[Instrument],
    events: list[TerminalEvent] | None,
    coverage_start: date | None = None,
    coverage_end: date | None = None,
    expected_delisted_ids: set[str] | None = None,
) -> DelistedCoverageReport:
    """Derive measurable delisted coverage — never promote PARTIAL→FULL on active-only universe."""
    events = list(events or [])
    delisted = [i for i in instruments if i.delisting_date is not None]
    delist_events = [e for e in events if e.event_type == TerminalEventType.DELISTING]
    by_id = {e.instrument_id: e for e in delist_events}

    notes: list[str] = []
    if not events and not delisted:
        return DelistedCoverageReport(
            known_instruments=len(instruments),
            known_delisted_instruments=0,
            terminal_events=0,
            delisting_events=0,
            coverage_start=coverage_start.isoformat() if coverage_start else None,
            coverage_end=coverage_end.isoformat() if coverage_end else None,
            coverage_ratio=0.0,
            evidence_status="none",
            level=DelistedCoverage.NONE.value,
            notes=["no terminal ledger and no delisting_date on instruments"],
        )

    expected = expected_delisted_ids
    if expected is None:
        expected = {(i.instrument_id or i.symbol) for i in delisted}

    if not expected:
        # Events without any delisted instruments → partial evidence only
        notes.append("terminal events present but no expected delisted set")
        return DelistedCoverageReport(
            known_instruments=len(instruments),
            known_delisted_instruments=0,
            terminal_events=len(events),
            delisting_events=len(delist_events),
            coverage_start=coverage_start.isoformat() if coverage_start else None,
            coverage_end=coverage_end.isoformat() if coverage_end else None,
            coverage_ratio=0.0 if not delist_events else 0.5,
            evidence_status="partial",
            level=DelistedCoverage.PARTIAL.value,
            notes=notes,
        )

    matched = 0
    verified_matched = 0
    for iid in expected:
        ev = by_id.get(iid)
        if ev is None:
            continue
        matched += 1
        if ev.verification_status == "verified":
            verified_matched += 1

    ratio = matched / len(expected) if expected else 0.0
    if matched == 0:
        level = DelistedCoverage.UNKNOWN.value
        status = "unknown"
        notes.append("delisted instruments lack matching TerminalEvent.DELISTING")
    elif matched == len(expected) and verified_matched == len(expected):
        level = DelistedCoverage.COMPLETE.value
        status = "complete"
    else:
        level = DelistedCoverage.PARTIAL.value
        status = "partial"
        notes.append(
            "PARTIAL must not be treated as FULL merely because the active universe looks complete"
        )

    return DelistedCoverageReport(
        known_instruments=len(instruments),
        known_delisted_instruments=len(delisted),
        terminal_events=len(events),
        delisting_events=len(delist_events),
        coverage_start=coverage_start.isoformat() if coverage_start else None,
        coverage_end=coverage_end.isoformat() if coverage_end else None,
        coverage_ratio=ratio,
        evidence_status=status,
        level=level,
        notes=notes,
    )

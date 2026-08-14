"""Research-universe coverage metrics and fail-closed eligibility verdict.

Aggregates the mandated coverage signals for the PIT universe layer:

- ``membership_coverage_ratio``    — known (TRUE/FALSE) ÷ total membership queries
- ``instrument_identity_coverage`` — fraction with authoritative exchange:ISIN
- ``delisted_coverage``            — measurable terminal-event coverage level
- ``unknown_membership_count``     — sessions×instruments answered UNKNOWN
- ``research_eligibility``         — universe-layer readiness (fails closed)

The eligibility verdict here is a *universe-layer* readiness gate. It NEVER
enables paper or live trading, and it does not override the central dataset
certification gate — it only reports whether the PIT universe itself is
research-grade. Any missing evidence keeps the verdict False.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.instruments.coverage import measure_delisted_coverage
from quantfund.data.instruments.delisted import TerminalEvent
from quantfund.data.models import Instrument
from quantfund.data.policy import DelistedCoverage
from quantfund.data.universe.coverage import compute_membership_coverage
from quantfund.data.universe.membership import detect_current_snapshot_used_as_history
from quantfund.data.universe.models import UniverseCompleteness, UniverseVersion
from quantfund.research.universe.identity import (
    bind_identity,
    instrument_identity_coverage,
)

# Fail-closed thresholds. Not toggles — documented policy for research grade.
_MEMBERSHIP_COVERAGE_REQUIRED = 1.0
_IDENTITY_COVERAGE_REQUIRED = 1.0
_ACCEPTABLE_DELISTED_LEVELS = frozenset(
    {DelistedCoverage.PARTIAL.value, DelistedCoverage.COMPLETE.value}
)
_ACCEPTABLE_COMPLETENESS = frozenset(
    {UniverseCompleteness.PARTIAL_PIT, UniverseCompleteness.FULL_PIT}
)


@dataclass(frozen=True)
class ResearchUniverseCoverage:
    universe_id: str
    universe_version: str
    completeness: str
    start: str
    end: str
    session_count: int
    instrument_count: int
    membership_coverage_ratio: float
    unknown_membership_count: int
    true_membership_sessions: int
    false_membership_sessions: int
    instrument_identity_coverage: float
    authoritative_identity_count: int
    delisted_coverage: str
    delisted_coverage_ratio: float
    delisted_known_instruments: int
    research_eligibility: bool
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "universe_id": self.universe_id,
            "universe_version": self.universe_version,
            "completeness": self.completeness,
            "start": self.start,
            "end": self.end,
            "session_count": self.session_count,
            "instrument_count": self.instrument_count,
            "membership_coverage_ratio": self.membership_coverage_ratio,
            "unknown_membership_count": self.unknown_membership_count,
            "true_membership_sessions": self.true_membership_sessions,
            "false_membership_sessions": self.false_membership_sessions,
            "instrument_identity_coverage": self.instrument_identity_coverage,
            "authoritative_identity_count": self.authoritative_identity_count,
            "delisted_coverage": self.delisted_coverage,
            "delisted_coverage_ratio": self.delisted_coverage_ratio,
            "delisted_known_instruments": self.delisted_known_instruments,
            "research_eligibility": self.research_eligibility,
            "blockers": list(self.blockers),
            "notes": list(self.notes),
        }


def evaluate_research_universe_coverage(
    universe: UniverseVersion,
    *,
    calendar: CalendarProvider,
    start: date,
    end: date,
    instruments: dict[str, Instrument] | None = None,
    terminal_events: list[TerminalEvent] | None = None,
) -> ResearchUniverseCoverage:
    """Compute coverage metrics and a fail-closed research-eligibility verdict."""
    instruments = instruments or {}
    blockers: list[str] = []
    notes: list[str] = []

    membership = compute_membership_coverage(
        universe, calendar=calendar, start=start, end=end
    )

    bindings = [bind_identity(inst) for inst in instruments.values()]
    identity_cov = instrument_identity_coverage(bindings)
    authoritative_identity_count = sum(1 for b in bindings if b.is_authoritative)

    delisted = measure_delisted_coverage(
        instruments=list(instruments.values()),
        events=terminal_events,
        coverage_start=start,
        coverage_end=end,
    )

    # --- Fail-closed eligibility evaluation -------------------------------
    if universe.completeness not in _ACCEPTABLE_COMPLETENESS:
        blockers.append("universe_not_point_in_time")
    if detect_current_snapshot_used_as_history(
        universe, historical_start=start, historical_end=end
    ):
        blockers.append("current_snapshot_used_as_history")
    if membership.membership_coverage_ratio < _MEMBERSHIP_COVERAGE_REQUIRED:
        blockers.append("membership_coverage_below_1.0")
    if membership.unknown_membership_sessions > 0:
        blockers.append("unknown_membership_sessions_gt_0")
    if not instruments:
        blockers.append("no_instrument_identity_records")
    if identity_cov < _IDENTITY_COVERAGE_REQUIRED:
        blockers.append("instrument_identity_coverage_below_1.0")
    if delisted.level not in _ACCEPTABLE_DELISTED_LEVELS:
        blockers.append("delisted_coverage_insufficient")

    if not blockers:
        notes.append("universe layer is research-grade for the measured window")
    else:
        notes.append(
            "research eligibility FALSE — one or more PIT universe blockers unresolved"
        )

    return ResearchUniverseCoverage(
        universe_id=universe.universe_id,
        universe_version=universe.universe_version,
        completeness=universe.completeness.value,
        start=start.isoformat(),
        end=end.isoformat(),
        session_count=membership.session_count,
        instrument_count=membership.instrument_count,
        membership_coverage_ratio=membership.membership_coverage_ratio,
        unknown_membership_count=membership.unknown_membership_sessions,
        true_membership_sessions=membership.true_sessions,
        false_membership_sessions=membership.false_sessions,
        instrument_identity_coverage=identity_cov,
        authoritative_identity_count=authoritative_identity_count,
        delisted_coverage=delisted.level,
        delisted_coverage_ratio=delisted.coverage_ratio,
        delisted_known_instruments=delisted.known_instruments,
        research_eligibility=not blockers,
        blockers=blockers,
        notes=notes,
    )

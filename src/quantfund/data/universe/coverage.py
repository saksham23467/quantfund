"""Point-in-time membership coverage metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.universe.membership import MembershipAnswer, was_member
from quantfund.data.universe.models import UniverseVersion


@dataclass(frozen=True)
class MembershipCoverage:
    known_membership_sessions: int
    unknown_membership_sessions: int
    true_sessions: int
    false_sessions: int
    membership_coverage_ratio: float
    instrument_count: int
    session_count: int

    def to_dict(self) -> dict:
        return {
            "known_membership_sessions": self.known_membership_sessions,
            "unknown_membership_sessions": self.unknown_membership_sessions,
            "true_sessions": self.true_sessions,
            "false_sessions": self.false_sessions,
            "membership_coverage_ratio": self.membership_coverage_ratio,
            "instrument_count": self.instrument_count,
            "session_count": self.session_count,
        }


def compute_membership_coverage(
    universe: UniverseVersion,
    *,
    calendar: CalendarProvider,
    start: date,
    end: date,
    instrument_ids: list[str] | None = None,
    symbols: list[str] | None = None,
) -> MembershipCoverage:
    """Measure known vs UNKNOWN membership over open sessions × instruments."""
    sessions = calendar.sessions_in_range(start, end)
    ids = list(instrument_ids or [])
    syms = list(symbols or [])
    if not ids and not syms:
        if universe.memberships:
            ids = sorted({m.instrument_id for m in universe.memberships})
            syms = sorted({m.symbol for m in universe.memberships})
        else:
            ids = list(universe.instrument_ids)
            syms = list(universe.symbols)

    # Prefer instrument_id queries when available
    keys: list[tuple[str | None, str | None]] = []
    if ids:
        keys = [(i, None) for i in ids]
    else:
        keys = [(None, s) for s in syms]

    known = unknown = true_n = false_n = 0
    for sess in sessions:
        for iid, sym in keys:
            ans = was_member(universe, instrument_id=iid, symbol=sym, on=sess)
            if ans == MembershipAnswer.UNKNOWN:
                unknown += 1
            else:
                known += 1
                if ans == MembershipAnswer.TRUE:
                    true_n += 1
                else:
                    false_n += 1

    total = known + unknown
    ratio = (known / total) if total else 1.0
    return MembershipCoverage(
        known_membership_sessions=known,
        unknown_membership_sessions=unknown,
        true_sessions=true_n,
        false_sessions=false_n,
        membership_coverage_ratio=ratio,
        instrument_count=len(keys),
        session_count=len(sessions),
    )

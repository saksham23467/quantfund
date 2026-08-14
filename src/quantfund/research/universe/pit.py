"""Point-in-time research universe resolution.

This layer sits on top of :mod:`quantfund.data.universe` PIT membership
primitives and answers the research question: *"which instruments were in the
universe on date D?"* — with three strict guarantees:

1. Point-in-time: membership is resolved from dated interval evidence, never
   from today's constituent list. A current snapshot applied across history is
   rejected (see :func:`quantfund.data.universe.detect_current_snapshot_used_as_history`).
2. Survivorship-safe: a security that was a member on D but is delisted *after*
   D is still returned as a member on D. Delisting never erases history.
3. Fail closed: when membership evidence does not cover ``as_of`` the answer is
   UNKNOWN and the instrument is placed in ``unknown`` — never silently TRUE and
   never silently FALSE.

Corporate actions and RAW execution prices are deliberately out of scope here:
this module only touches membership + identity, so it can never blend adjusted
and raw prices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from quantfund.data.models import Instrument
from quantfund.data.universe.membership import (
    MembershipAnswer,
    detect_current_snapshot_used_as_history,
    was_member,
)
from quantfund.data.universe.models import UniverseCompleteness, UniverseVersion
from quantfund.research.universe.identity import IdentityBinding, bind_identity


@dataclass(frozen=True)
class PITMember:
    """A single resolved universe member as-of a point-in-time date."""

    instrument_id: str
    symbol: str
    answer: MembershipAnswer
    identity: IdentityBinding | None
    delisted: bool
    delisting_date: date | None

    def to_dict(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "symbol": self.symbol,
            "answer": self.answer.value,
            "identity": self.identity.to_dict() if self.identity else None,
            "delisted": self.delisted,
            "delisting_date": self.delisting_date.isoformat() if self.delisting_date else None,
        }


@dataclass(frozen=True)
class PITUniverseSnapshot:
    """The resolved universe as-of a single date.

    ``members`` are TRUE members only. ``unknown`` and ``excluded`` are kept
    separate so callers can never confuse "not known to be a member" with
    "known not to be a member".
    """

    as_of: date
    universe_id: str
    universe_version: str
    completeness: UniverseCompleteness
    members: list[PITMember]
    unknown: list[PITMember]
    excluded: list[PITMember]
    warnings: list[str] = field(default_factory=list)

    @property
    def member_symbols(self) -> list[str]:
        return sorted(m.symbol for m in self.members)

    @property
    def member_instrument_ids(self) -> list[str]:
        return sorted(m.instrument_id for m in self.members)

    @property
    def unknown_count(self) -> int:
        return len(self.unknown)

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of.isoformat(),
            "universe_id": self.universe_id,
            "universe_version": self.universe_version,
            "completeness": self.completeness.value,
            "member_count": len(self.members),
            "unknown_count": len(self.unknown),
            "excluded_count": len(self.excluded),
            "members": [m.to_dict() for m in self.members],
            "unknown": [m.to_dict() for m in self.unknown],
            "warnings": list(self.warnings),
        }


def _roster_keys(
    universe: UniverseVersion,
    instruments: dict[str, Instrument],
) -> list[tuple[str, str]]:
    """(instrument_id, symbol) pairs to evaluate: universe roster ∪ instruments."""
    pairs: dict[str, str] = {}
    if universe.memberships:
        for m in universe.memberships:
            pairs.setdefault(m.instrument_id, m.symbol)
    for m in universe.members:
        pairs.setdefault(m.instrument_id, m.symbol)
    for iid, inst in instruments.items():
        pairs.setdefault(iid, inst.symbol)
    return sorted(pairs.items())


def resolve_pit_universe(
    universe: UniverseVersion,
    *,
    as_of: date,
    instruments: dict[str, Instrument] | None = None,
) -> PITUniverseSnapshot:
    """Resolve the point-in-time universe on ``as_of``.

    ``instruments`` maps ``instrument_id`` → :class:`Instrument` and supplies
    stable identity + delisting metadata. It is optional; identity is UNKNOWN
    for any member without a matching instrument record.
    """
    instruments = instruments or {}
    warnings: list[str] = list(universe.warnings)

    # A current snapshot must never masquerade as historical membership.
    if detect_current_snapshot_used_as_history(
        universe, historical_start=as_of, historical_end=as_of
    ):
        warnings.append(
            "current_snapshot_only universe queried off its as_of_date — "
            "membership is UNKNOWN, not the snapshot roster"
        )

    members: list[PITMember] = []
    unknown: list[PITMember] = []
    excluded: list[PITMember] = []

    for instrument_id, symbol in _roster_keys(universe, instruments):
        answer = was_member(
            universe, instrument_id=instrument_id, symbol=symbol, on=as_of
        )
        inst = instruments.get(instrument_id)
        identity = bind_identity(inst) if inst is not None else None
        delisting_date = inst.delisting_date if inst is not None else None
        delisted = delisting_date is not None
        pit = PITMember(
            instrument_id=instrument_id,
            symbol=symbol,
            answer=answer,
            identity=identity,
            delisted=delisted,
            delisting_date=delisting_date,
        )
        if answer == MembershipAnswer.TRUE:
            members.append(pit)
        elif answer == MembershipAnswer.UNKNOWN:
            unknown.append(pit)
        else:
            excluded.append(pit)

    return PITUniverseSnapshot(
        as_of=as_of,
        universe_id=universe.universe_id,
        universe_version=universe.universe_version,
        completeness=universe.completeness,
        members=members,
        unknown=unknown,
        excluded=excluded,
        warnings=warnings,
    )

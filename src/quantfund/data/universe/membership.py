"""Point-in-time membership queries with TRUE / FALSE / UNKNOWN."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path

from quantfund.data.universe.models import (
    SURVIVORSHIP_WARNING,
    UniverseCompleteness,
    UniverseMember,
    UniverseMembership,
    UniverseVersion,
    VerificationStatus,
)


class MembershipAnswer(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


def was_member(
    universe: UniverseVersion,
    *,
    instrument_id: str | None = None,
    symbol: str | None = None,
    on: date,
) -> MembershipAnswer:
    """Return whether an instrument was in the universe on ``on``.

    Stage A (current_snapshot_only):
    - on == as_of_date and in member list → TRUE/FALSE
    - on != as_of_date → UNKNOWN (never invent historical membership)

    PIT (partial_pit / full_pit) with memberships[] intervals:
    - covering verified interval → TRUE
    - covering unverified interval under partial_pit → UNKNOWN
    - tracked name, no covering interval inside coverage → FALSE
    - untracked name under partial_pit → UNKNOWN (never invent)
    - untracked name under full_pit → FALSE
    - outside coverage → UNKNOWN

    UNKNOWN remains distinct from FALSE.
    """
    if instrument_id is None and symbol is None:
        raise ValueError("instrument_id or symbol required")

    if universe.completeness == UniverseCompleteness.CURRENT_SNAPSHOT_ONLY:
        ids = {m.instrument_id for m in universe.members}
        syms = {m.symbol for m in universe.members}

        def in_snapshot() -> bool:
            if instrument_id is not None and instrument_id in ids:
                return True
            if symbol is not None and symbol in syms:
                return True
            return False

        if on != universe.as_of_date:
            return MembershipAnswer.UNKNOWN
        return MembershipAnswer.TRUE if in_snapshot() else MembershipAnswer.FALSE

    # Interval-based PIT
    if universe.memberships:
        coverage_start = universe.effective_start
        coverage_end = universe.effective_end
        if coverage_start is not None and on < coverage_start:
            return MembershipAnswer.UNKNOWN
        if coverage_end is not None and on > coverage_end:
            return MembershipAnswer.UNKNOWN

        def _matches_identity(m: UniverseMembership) -> bool:
            if instrument_id is not None and m.instrument_id == instrument_id:
                return True
            if symbol is not None and m.symbol == symbol:
                return True
            return False

        matching = [
            m for m in universe.memberships if m.covers(on) and _matches_identity(m)
        ]
        if matching:
            # Unverified covering intervals under partial_pit ⇒ UNKNOWN (not TRUE)
            if all(m.verification_status == VerificationStatus.UNVERIFIED for m in matching):
                if universe.completeness == UniverseCompleteness.PARTIAL_PIT:
                    return MembershipAnswer.UNKNOWN
            return MembershipAnswer.TRUE

        related = [m for m in universe.memberships if _matches_identity(m)]
        in_coverage = coverage_start is not None and (
            coverage_end is None or coverage_start <= on <= coverage_end
        )
        if not in_coverage:
            return MembershipAnswer.UNKNOWN

        # Known instrument with intervals that do not cover ``on`` ⇒ FALSE
        if related:
            return MembershipAnswer.FALSE

        # Instrument absent from a PARTIAL roster ⇒ UNKNOWN (do not invent FALSE)
        if universe.completeness == UniverseCompleteness.PARTIAL_PIT:
            return MembershipAnswer.UNKNOWN

        # FULL_PIT complete roster: absence inside coverage ⇒ FALSE
        return MembershipAnswer.FALSE

    # Fallback: snapshot members valid only within effective window
    start = universe.effective_start or universe.as_of_date
    end = universe.effective_end
    if on < start:
        return MembershipAnswer.UNKNOWN
    if end is not None and on > end:
        return MembershipAnswer.UNKNOWN
    ids = {m.instrument_id for m in universe.members}
    syms = {m.symbol for m in universe.members}
    in_snap = (instrument_id in ids if instrument_id else False) or (
        symbol in syms if symbol else False
    )
    return MembershipAnswer.TRUE if in_snap else MembershipAnswer.FALSE


def detect_current_snapshot_used_as_history(
    universe: UniverseVersion,
    *,
    historical_start: date,
    historical_end: date,
) -> bool:
    """True if a Stage A snapshot is being applied across a historical range."""
    if universe.completeness != UniverseCompleteness.CURRENT_SNAPSHOT_ONLY:
        return False
    return historical_start < universe.as_of_date or historical_end > universe.as_of_date


class UniverseMembershipStore:
    """Persist / load versioned universe membership files."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, universe_id: str, universe_version: str) -> Path:
        return self.root / universe_id / f"universe_version={universe_version}" / "membership.json"

    def save(self, universe: UniverseVersion) -> Path:
        path = self.path_for(universe.universe_id, universe.universe_version)
        if path.exists():
            raise FileExistsError(
                f"Universe membership version immutable: {path}. "
                "Bump universe_version for new membership evidence."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = universe.model_dump(mode="json")
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        meta = {
            "universe_id": universe.universe_id,
            "universe_version": universe.universe_version,
            "completeness": universe.completeness.value,
            "as_of_date": universe.as_of_date.isoformat(),
            "warnings": universe.warnings,
            "survivorship_warning": SURVIVORSHIP_WARNING,
            "membership_interval_count": len(universe.memberships),
            "immutable": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (path.parent / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return path

    def load(self, universe_id: str, universe_version: str) -> UniverseVersion:
        path = self.path_for(universe_id, universe_version)
        data = json.loads(path.read_text(encoding="utf-8"))
        return UniverseVersion.model_validate(data)


def build_stage_a_snapshot(
    *,
    universe_id: str,
    universe_version: str,
    as_of_date: date,
    members: list[UniverseMember],
    source: str,
    name: str | None = None,
) -> UniverseVersion:
    """Construct a Stage A current_snapshot_only universe version."""
    return UniverseVersion(
        universe_id=universe_id,
        universe_version=universe_version,
        completeness=UniverseCompleteness.CURRENT_SNAPSHOT_ONLY,
        as_of_date=as_of_date,
        effective_start=as_of_date,
        effective_end=as_of_date,
        source=source,
        members=members,
        created_at=datetime.now(timezone.utc),
        notes=(
            f"Stage A snapshot for {name or universe_id}. "
            "Does not represent historical index membership."
        ),
    )


def build_pit_universe(
    *,
    universe_id: str,
    universe_version: str,
    memberships: list[UniverseMembership],
    as_of_date: date,
    effective_start: date,
    effective_end: date,
    source: str,
    completeness: UniverseCompleteness = UniverseCompleteness.PARTIAL_PIT,
    verification_status: VerificationStatus = VerificationStatus.PARTIAL,
) -> UniverseVersion:
    """Construct a PIT universe from interval memberships."""
    return UniverseVersion(
        universe_id=universe_id,
        universe_version=universe_version,
        completeness=completeness,
        as_of_date=as_of_date,
        effective_start=effective_start,
        effective_end=effective_end,
        source=source,
        memberships=memberships,
        verification_status=verification_status,
        created_at=datetime.now(timezone.utc),
        notes="Point-in-time membership intervals. UNKNOWN outside coverage.",
    )

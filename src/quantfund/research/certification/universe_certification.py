"""Point-in-time universe membership certification (TRUE/FALSE/UNKNOWN)."""

from __future__ import annotations

from datetime import date

from quantfund.research.certification.results import CertResult
from quantfund.research.data_contract.models import (
    MembershipRecord,
    ResearchDatasetPackage,
)


def membership_state(
    symbol: str, on: date, by_symbol: dict[str, list[MembershipRecord]]
) -> str:
    """Answer 'was symbol a member on date?' as TRUE / FALSE / UNKNOWN.

    - No ledger at all for this symbol => UNKNOWN (never assume today's roster).
    - Ledger present => TRUE inside an interval, FALSE outside (pre/post).
    """
    recs = by_symbol.get(symbol)
    if not recs:
        return "UNKNOWN"
    for rec in recs:
        if rec.member_from <= on and (rec.member_to is None or on <= rec.member_to):
            return "TRUE"
    return "FALSE"


def certify_universe(package: ResearchDatasetPackage) -> CertResult:
    by_symbol: dict[str, list[MembershipRecord]] = {}
    for rec in package.membership:
        by_symbol.setdefault(rec.symbol, []).append(rec)

    total = 0
    known = 0
    unknown = 0
    for bar in package.ohlcv:
        total += 1
        state = membership_state(bar.symbol, bar.date, by_symbol)
        if state == "UNKNOWN":
            unknown += 1
        else:
            known += 1

    ratio = (known / total) if total else 0.0

    coverage_start = package.manifest.coverage_start
    snapshot_like = bool(package.membership) and all(
        r.member_to is None for r in package.membership
    ) and min((r.member_from for r in package.membership), default=coverage_start) > coverage_start

    if not package.membership:
        completeness = "none"
    elif snapshot_like:
        # A single current roster stamped after the window begins = today's
        # constituents standing in for history. Never acceptable.
        completeness = "current_snapshot_only"
    elif unknown == 0:
        completeness = "full_pit"
    else:
        completeness = "partial_pit"

    blockers: list[str] = []
    if unknown > 0:
        blockers.append(f"unknown_membership_session_count={unknown}")
    if ratio < 1.0:
        blockers.append(f"membership_coverage_ratio={ratio} < 1.0")
    if completeness == "none":
        blockers.append("no PIT membership ledger (universe_completeness=none)")
    if completeness == "current_snapshot_only":
        blockers.append(
            "universe_completeness=current_snapshot_only "
            "(today's roster must not stand in for history)"
        )

    return CertResult(
        dimension="pit_universe",
        passed=not blockers,
        metrics={
            "membership_coverage_ratio": ratio,
            "unknown_membership_session_count": unknown,
            "universe_completeness": completeness,
            "evaluated_pairs": total,
        },
        blockers=blockers,
    )

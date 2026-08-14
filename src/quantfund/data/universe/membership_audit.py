"""Audit PIT membership intervals for overlaps, gaps, and duplicates (Phase 7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from quantfund.data.universe.models import UniverseMembership, UniverseVersion


@dataclass
class MembershipAuditIssue:
    code: str
    message: str
    instrument_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MembershipAuditReport:
    issues: list[MembershipAuditIssue]
    duplicate_count: int
    overlap_count: int
    gap_count: int
    interval_count: int

    @property
    def ok(self) -> bool:
        return self.duplicate_count == 0 and self.overlap_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "duplicate_count": self.duplicate_count,
            "overlap_count": self.overlap_count,
            "gap_count": self.gap_count,
            "interval_count": self.interval_count,
            "issues": [
                {
                    "code": i.code,
                    "message": i.message,
                    "instrument_id": i.instrument_id,
                    "details": i.details,
                }
                for i in self.issues
            ],
        }


def _intervals_overlap(a: UniverseMembership, b: UniverseMembership) -> bool:
    a_end = a.member_to or date.max
    b_end = b.member_to or date.max
    return a.member_from <= b_end and b.member_from <= a_end


def audit_membership_intervals(
    memberships: list[UniverseMembership],
    *,
    coverage_start: date | None = None,
    coverage_end: date | None = None,
) -> MembershipAuditReport:
    """Detect duplicates, overlapping intervals, and coverage gaps per instrument."""
    issues: list[MembershipAuditIssue] = []
    duplicate_count = 0
    overlap_count = 0
    gap_count = 0

    # Exact duplicate rows
    seen_keys: set[tuple] = set()
    unique: list[UniverseMembership] = []
    for m in memberships:
        key = (
            m.instrument_id,
            m.symbol,
            m.member_from.isoformat(),
            m.member_to.isoformat() if m.member_to else None,
            m.source,
        )
        if key in seen_keys:
            duplicate_count += 1
            issues.append(
                MembershipAuditIssue(
                    code="duplicate_membership",
                    message=f"Duplicate membership interval for {m.instrument_id}",
                    instrument_id=m.instrument_id,
                    details={"symbol": m.symbol},
                )
            )
        else:
            seen_keys.add(key)
            unique.append(m)

    by_id: dict[str, list[UniverseMembership]] = {}
    for m in unique:
        by_id.setdefault(m.instrument_id, []).append(m)

    for iid, rows in by_id.items():
        rows_sorted = sorted(rows, key=lambda r: r.member_from)
        for i in range(len(rows_sorted)):
            for j in range(i + 1, len(rows_sorted)):
                if _intervals_overlap(rows_sorted[i], rows_sorted[j]):
                    # Adjacent end+1 == start is OK if no day overlap
                    a, b = rows_sorted[i], rows_sorted[j]
                    if a.member_to is not None and b.member_from == date.fromordinal(
                        a.member_to.toordinal() + 1
                    ):
                        continue
                    if a.member_to is not None and b.member_from > a.member_to:
                        continue
                    overlap_count += 1
                    issues.append(
                        MembershipAuditIssue(
                            code="overlapping_membership",
                            message=f"Overlapping membership intervals for {iid}",
                            instrument_id=iid,
                            details={
                                "a": a.member_from.isoformat(),
                                "b": b.member_from.isoformat(),
                            },
                        )
                    )
        # Gaps between consecutive intervals (informational)
        for i in range(len(rows_sorted) - 1):
            cur, nxt = rows_sorted[i], rows_sorted[i + 1]
            if cur.member_to is None:
                continue
            expected_next = date.fromordinal(cur.member_to.toordinal() + 1)
            if nxt.member_from > expected_next:
                gap_count += 1
                issues.append(
                    MembershipAuditIssue(
                        code="membership_gap",
                        message=f"Gap in membership for {iid}",
                        instrument_id=iid,
                        details={
                            "gap_start": expected_next.isoformat(),
                            "gap_end": date.fromordinal(
                                nxt.member_from.toordinal() - 1
                            ).isoformat(),
                        },
                    )
                )

    # Coverage window gaps (instrument absent entirely is NOT invented as FALSE)
    if coverage_start and coverage_end and not unique:
        issues.append(
            MembershipAuditIssue(
                code="empty_membership_file",
                message="No membership intervals in declared coverage window",
            )
        )

    return MembershipAuditReport(
        issues=issues,
        duplicate_count=duplicate_count,
        overlap_count=overlap_count,
        gap_count=gap_count,
        interval_count=len(unique),
    )


def audit_universe_version(universe: UniverseVersion) -> MembershipAuditReport:
    return audit_membership_intervals(
        list(universe.memberships),
        coverage_start=universe.effective_start,
        coverage_end=universe.effective_end,
    )

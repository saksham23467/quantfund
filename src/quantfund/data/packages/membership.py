"""Resolve PIT universe membership for a research package.

Prefer package-local membership files. Never invent historical membership.
Falls back to the repository universe store only when package has no membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from quantfund.config import PATHS
from quantfund.data.models import Instrument
from quantfund.data.universe.import_membership import build_universe_from_membership_file
from quantfund.data.universe.membership_audit import (
    MembershipAuditReport,
    audit_membership_intervals,
)
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMembership,
    UniverseVersion,
    VerificationStatus,
)


MEMBERSHIP_CANDIDATES = (
    "universe/membership.json",
    "universe/membership.csv",
    "universe/nifty50/membership.json",
    "universe/nifty50/membership.csv",
    "membership.json",
    "membership.csv",
)


@dataclass
class PackageUniverseResolution:
    universe: UniverseVersion
    source: str  # package | repository | synthetic_fallback
    membership_path: Path | None
    audit: MembershipAuditReport | None
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "membership_path": str(self.membership_path) if self.membership_path else None,
            "universe_id": self.universe.universe_id,
            "universe_version": self.universe.universe_version,
            "completeness": self.universe.completeness.value,
            "audit": self.audit.to_dict() if self.audit else None,
            "notes": list(self.notes),
        }


def discover_package_membership_path(package_root: Path) -> Path | None:
    root = Path(package_root)
    for rel in MEMBERSHIP_CANDIDATES:
        path = root / rel
        if path.is_file():
            return path
    # Also accept universe/<id>/universe_version=*/membership.json layout
    uni = root / "universe"
    if uni.is_dir():
        for path in sorted(uni.rglob("membership.json")):
            if path.is_file():
                return path
        for path in sorted(uni.rglob("membership.csv")):
            if path.is_file():
                return path
    return None


def resolve_package_universe(
    package_root: Path,
    *,
    instruments: list[Instrument],
    start: date,
    end: date,
    universe_id: str = "nifty50",
    allow_repository_fallback: bool = True,
    allow_synthetic_fallback: bool = True,
) -> PackageUniverseResolution:
    """Load PIT membership for certification. Fail closed on overlapping intervals."""
    notes: list[str] = []
    root = Path(package_root)
    membership_path = discover_package_membership_path(root)

    if membership_path is not None:
        try:
            # JSON payload may set completeness=full_pit; CSV default remains partial_pit.
            universe = build_universe_from_membership_file(
                membership_path,
                universe_id=universe_id,
                universe_version=f"package_{membership_path.stem}",
                effective_start=start,
                effective_end=end,
                source="package_membership",
                completeness=UniverseCompleteness.PARTIAL_PIT,
                verification_status=VerificationStatus.PARTIAL,
                as_of_date=end,
            )
        except ValueError as exc:
            # Surface audit failures as empty-ish resolution via re-raise for certify
            raise ValueError(f"package_membership_invalid:{exc}") from exc

        audit = audit_membership_intervals(
            list(universe.memberships),
            coverage_start=start,
            coverage_end=end,
        )
        if not audit.ok:
            raise ValueError(
                "package_membership_audit_failed:"
                f"duplicates={audit.duplicate_count} overlaps={audit.overlap_count}"
            )
        notes.append(f"Using package membership: {membership_path.relative_to(root)}")
        return PackageUniverseResolution(
            universe=universe,
            source="package",
            membership_path=membership_path,
            audit=audit,
            notes=notes,
        )

    notes.append("No package-local membership file found")

    if allow_repository_fallback:
        membership_repo = (
            PATHS.data_dir
            / "universes"
            / "nifty50"
            / "universe_version=pit_partial_documented_v1"
            / "membership.json"
        )
        if membership_repo.exists():
            from quantfund.data.universe.membership import UniverseMembershipStore

            universe = UniverseMembershipStore(PATHS.data_dir / "universes").load(
                "nifty50", "pit_partial_documented_v1"
            )
            audit = audit_membership_intervals(
                list(universe.memberships),
                coverage_start=start,
                coverage_end=end,
            )
            notes.append(
                "Fallback: repository pit_partial_documented_v1 "
                "(may produce UNKNOWN for symbols outside documented roster)"
            )
            return PackageUniverseResolution(
                universe=universe,
                source="repository",
                membership_path=membership_repo,
                audit=audit,
                notes=notes,
            )

    if not allow_synthetic_fallback:
        raise ValueError("membership_missing:no_package_or_repository_membership")

    # Last resort: open-ended unverified intervals — NEVER research-grade proof
    from quantfund.data.universe.membership import build_pit_universe

    universe = build_pit_universe(
        universe_id=universe_id,
        universe_version="synthetic_fallback_unverified",
        memberships=[
            UniverseMembership(
                universe_id=universe_id,
                instrument_id=i.instrument_id or i.symbol,
                symbol=i.symbol,
                member_from=start,
                member_to=None,
                source="synthetic_fallback",
                verification_status=VerificationStatus.UNVERIFIED,
            )
            for i in instruments
        ],
        as_of_date=end,
        effective_start=start,
        effective_end=end,
        source="synthetic_fallback",
        completeness=UniverseCompleteness.PARTIAL_PIT,
    )
    notes.append(
        "Synthetic fallback membership (unverified open intervals) — "
        "cannot prove RESEARCH_ELIGIBLE PIT"
    )
    return PackageUniverseResolution(
        universe=universe,
        source="synthetic_fallback",
        membership_path=None,
        audit=None,
        notes=notes,
    )

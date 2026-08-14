"""Import historical universe membership intervals from documented CSV/JSON.

Never invent membership. Rows without verification_status default to unverified.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from quantfund.data.universe.membership import build_pit_universe
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMembership,
    UniverseVersion,
    VerificationStatus,
)


def _parse_date(value: str | None) -> date | None:
    if value is None or value == "" or value.upper() == "NULL":
        return None
    return date.fromisoformat(value[:10])


def load_membership_csv(path: Path, *, universe_id: str) -> list[UniverseMembership]:
    """Load membership intervals from CSV.

    Required columns: instrument_id, symbol, member_from, source
    Optional: member_to, verification_status
    """
    rows: list[UniverseMembership] = []
    with Path(path).open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            status = (raw.get("verification_status") or "unverified").strip().lower()
            meta = {
                k: v
                for k, v in raw.items()
                if k
                not in {
                    "instrument_id",
                    "symbol",
                    "member_from",
                    "member_to",
                    "source",
                    "verification_status",
                    "evidence_reference",
                    "source_ref",
                }
                and v
            }
            evidence = (raw.get("evidence_reference") or raw.get("source_ref") or "").strip()
            if evidence:
                meta["evidence_reference"] = evidence
            rows.append(
                UniverseMembership(
                    universe_id=universe_id,
                    instrument_id=raw["instrument_id"].strip(),
                    symbol=raw["symbol"].strip(),
                    member_from=_parse_date(raw["member_from"]),  # type: ignore[arg-type]
                    member_to=_parse_date(raw.get("member_to")),
                    source=raw["source"].strip(),
                    verification_status=VerificationStatus(status),
                    metadata=meta,
                )
            )
    return rows


def build_universe_from_membership_file(
    path: Path,
    *,
    universe_id: str,
    universe_version: str,
    effective_start: date,
    effective_end: date,
    source: str,
    completeness: UniverseCompleteness = UniverseCompleteness.PARTIAL_PIT,
    verification_status: VerificationStatus = VerificationStatus.PARTIAL,
    as_of_date: date | None = None,
) -> UniverseVersion:
    path = Path(path)
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        memberships = [UniverseMembership.model_validate(r) for r in payload["memberships"]]
        completeness = UniverseCompleteness(
            payload.get("completeness", completeness.value)
        )
        verification_status = VerificationStatus(
            payload.get("verification_status", verification_status.value)
        )
        source = payload.get("source", source)
    else:
        memberships = load_membership_csv(path, universe_id=universe_id)

    # Never invent membership; audit duplicates/overlaps before build.
    from quantfund.data.universe.membership_audit import audit_membership_intervals

    audit = audit_membership_intervals(
        memberships,
        coverage_start=effective_start,
        coverage_end=effective_end,
    )
    if audit.duplicate_count or audit.overlap_count:
        raise ValueError(
            "Membership import failed audit: "
            f"duplicates={audit.duplicate_count} overlaps={audit.overlap_count} "
            f"issues={[i.code for i in audit.issues[:5]]}"
        )

    return build_pit_universe(
        universe_id=universe_id,
        universe_version=universe_version,
        memberships=memberships,
        as_of_date=as_of_date or effective_end,
        effective_start=effective_start,
        effective_end=effective_end,
        source=source,
        completeness=completeness,
        verification_status=verification_status,
    )

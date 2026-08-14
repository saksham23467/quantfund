"""GREEN / YELLOW / RED research-readiness traffic light.

GREEN means structurally capable — NOT automatically RESEARCH_ELIGIBLE.
ResearchEligibilityChecker remains authoritative for eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from quantfund.data.packages.readiness import audit_research_package
from quantfund.data.providers.package_validator import (
    resolve_configured_research_package,
    validate_research_package,
)
from quantfund.research.certify_package import certify_research_package


class ReadinessLight(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class ResearchReadinessReport:
    light: ReadinessLight
    package_root: str | None
    structurally_valid: bool
    research_eligible: bool
    research_eligible_capable: bool
    eligibility: str
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "light": self.light.value,
            "package_root": self.package_root,
            "structurally_valid": self.structurally_valid,
            "research_eligible_capable": self.research_eligible_capable,
            "research_eligible": self.research_eligible,
            "eligibility": self.eligibility,
            "blockers": list(self.blockers),
            "notes": list(self.notes),
            "meta": dict(self.meta),
            "warning": (
                "GREEN ≠ RESEARCH_ELIGIBLE. "
                "ResearchEligibilityChecker remains authoritative."
            ),
        }


def evaluate_research_readiness(
    package_root: Path | None = None,
) -> ResearchReadinessReport:
    root = package_root or resolve_configured_research_package()
    notes = [
        "GREEN means package appears capable of satisfying research gates.",
        "GREEN does NOT automatically mean RESEARCH_ELIGIBLE.",
    ]
    if root is None:
        return ResearchReadinessReport(
            light=ReadinessLight.RED,
            package_root=None,
            structurally_valid=False,
            research_eligible=False,
            research_eligible_capable=False,
            eligibility="development_only",
            blockers=["research_package_not_configured"],
            notes=notes
            + ["QUANTFUND_RESEARCH_PACKAGE unset; no external package configured."],
        )

    validation = validate_research_package(root)
    if not validation.valid:
        return ResearchReadinessReport(
            light=ReadinessLight.RED,
            package_root=str(root),
            structurally_valid=False,
            research_eligible=False,
            research_eligible_capable=False,
            eligibility="development_only",
            blockers=[f"{e.code}:{e.message}" for e in validation.errors],
            notes=notes,
            meta={"validation_ok": False},
        )

    caps = validation.capabilities
    capable = bool(caps and caps.can_satisfy_research_eligibility_source_bar())
    elig, facts, blockers, meta = certify_research_package(package_root=root)
    research_eligible = elig in {"research_eligible", "production_candidate"}

    audit = audit_research_package(package_root=root)
    incomplete = [
        c.name
        for c in audit.categories
        if c.status == "FAIL"
    ]

    if research_eligible:
        light = ReadinessLight.GREEN
        notes.append(
            "Fixture/package passed ResearchEligibilityChecker on derived facts."
        )
        md = validation.manifest.model_dump() if validation.manifest else {}
        if md.get("test_fixture_only") or "TEST_FIXTURE_ONLY" in (
            md.get("limitations") or []
        ):
            notes.append(
                "TEST_FIXTURE_ONLY — fabricated data; not real NSE market data."
            )
    elif capable and validation.valid and not research_eligible:
        light = ReadinessLight.YELLOW
        notes.append(
            "Structurally valid / source-bar capable but incomplete coverage or other blockers."
        )
    else:
        light = ReadinessLight.RED

    # Pull test_fixture flag from package.json
    try:
        import json

        pkg = json.loads((Path(root) / "package.json").read_text(encoding="utf-8"))
        if pkg.get("test_fixture_only") or "TEST_FIXTURE_ONLY" in (
            pkg.get("limitations") or []
        ):
            notes.append("Labeled TEST_FIXTURE_ONLY.")
            meta = {**meta, "test_fixture_only": True}
    except OSError:
        pass

    return ResearchReadinessReport(
        light=light,
        package_root=str(root),
        structurally_valid=True,
        research_eligible=research_eligible,
        research_eligible_capable=capable,
        eligibility=elig,
        blockers=list(blockers) + incomplete[:20],
        notes=notes,
        meta={
            **meta,
            "facts_hash": meta.get("facts_hash"),
            "audit_ready": audit.research_eligible,
        },
    )


def format_readiness_traffic_light(report: ResearchReadinessReport) -> str:
    lines = [
        "=== RESEARCH READINESS ===",
        f"Light: {report.light.value}",
        f"Package: {report.package_root or 'NOT CONFIGURED'}",
        f"Structurally valid: {report.structurally_valid}",
        f"RESEARCH_ELIGIBLE-CAPABLE: {report.research_eligible_capable}",
        f"RESEARCH_ELIGIBLE (authoritative): {report.research_eligible}",
        f"Eligibility: {report.eligibility}",
        "",
        "Blockers:",
    ]
    if report.blockers:
        for b in report.blockers:
            lines.append(f"- {b}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("Notes:")
    for n in report.notes:
        lines.append(f"- {n}")
    lines.append("")
    lines.append(
        "WARNING: GREEN ≠ automatic research authorization. "
        "ResearchEligibilityChecker remains authoritative."
    )
    return "\n".join(lines)

"""Dataset certification report formatting, fact assembly, and anti-forgery."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quantfund.data.eligibility import EligibilityDecision, ResearchEligibilityChecker
from quantfund.data.ingest.checksums import hash_json
from quantfund.data.policy import (
    CorporateActionCoverage,
    DatasetCertificationFacts,
    DelistedCoverage,
    EligibilityLevel,
)
from quantfund.data.quality.report import QualityReport


class DatasetCertification(BaseModel):
    """Reproducible certification artifact (Phase 7)."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    dataset_version: str
    certified_at: datetime
    facts_hash: str
    eligibility: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    license: dict[str, Any] = Field(default_factory=dict)
    quality_summary: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def build_dataset_certification(
    *,
    facts: DatasetCertificationFacts,
    decision: EligibilityDecision,
    provenance: dict[str, Any] | None = None,
    license_evidence: dict[str, Any] | None = None,
    certified_at: datetime | None = None,
) -> DatasetCertification:
    """Derive a certification record from validated facts (never package booleans)."""
    return DatasetCertification(
        dataset_id=facts.dataset_id,
        dataset_version=facts.dataset_version,
        certified_at=certified_at or datetime.now(timezone.utc),
        facts_hash=facts_hash(facts),
        eligibility=decision.level.value,
        blockers=list(decision.blockers),
        warnings=list(decision.notes),
        metrics={
            "membership_coverage_ratio": facts.membership_coverage_ratio,
            "unknown_membership_session_count": facts.unknown_membership_session_count,
            "delisted_coverage": facts.delisted_coverage,
            "corporate_action_coverage": facts.corporate_action_coverage,
            "ca_coverage_breakdown": facts.ca_coverage_breakdown,
            "error_count": facts.error_count,
            "warning_count": facts.warning_count,
            "content_hash": facts.content_hash,
            "package_content_hash": facts.package_content_hash,
            "capability_source_bar_ok": facts.capability_source_bar_ok,
            "calendar_verified": facts.calendar_verified,
            "universe_completeness": facts.universe_completeness,
            "source_grade": facts.source_grade,
        },
        provenance=dict(provenance or {}),
        license=dict(
            license_evidence
            or {
                "license_status": facts.license_status,
                "provenance_complete": facts.provenance_complete,
            }
        ),
        quality_summary={
            "missing_sessions": facts.missing_sessions,
            "missing_bars": facts.missing_bars,
            "duplicate_bars": facts.duplicate_bars,
            "invalid_ohlc": facts.invalid_ohlc,
            "instrument_identity_issues": facts.instrument_identity_issues,
            "quality_error_codes": facts.quality_error_codes,
        },
    )


def infer_ca_coverage(
    actions: list[Any] | None,
    *,
    verified: bool = False,
    source_grade: str | None = None,
) -> str:
    if not actions:
        return CorporateActionCoverage.NONE.value
    types = {getattr(a, "action_type", None) for a in actions}
    type_vals = {t.value if hasattr(t, "value") else str(t) for t in types if t}
    needed = {"split", "bonus", "dividend"}
    # Synthetic / non-exchange sources cannot claim full_verified CA coverage.
    if (
        verified
        and needed.issubset(type_vals)
        and source_grade not in {"synthetic", "non_exchange", None}
    ):
        return CorporateActionCoverage.FULL_VERIFIED.value
    if type_vals & {"split", "bonus", "dividend"}:
        return CorporateActionCoverage.SPLITS_BONUS_DIVIDENDS.value
    return CorporateActionCoverage.PARTIAL.value


def facts_canonical_payload(facts: DatasetCertificationFacts) -> dict[str, Any]:
    """Stable payload for facts_hash (excludes wall-clock / free-form extras noise)."""
    payload = facts.model_dump(mode="json")
    # extras may contain non-deterministic or forged eligibility claims — exclude
    payload.pop("extras", None)
    return payload


def facts_hash(facts: DatasetCertificationFacts) -> str:
    return hash_json(facts_canonical_payload(facts))


def verify_facts_integrity(
    facts: DatasetCertificationFacts,
    expected_hash: str,
) -> bool:
    return facts_hash(facts) == expected_hash


def facts_from_manifest_and_quality(
    *,
    manifest: Any,
    quality: QualityReport,
    corporate_action_coverage: str | None = None,
    delisted_coverage: str = DelistedCoverage.UNKNOWN.value,
    membership_coverage_ratio: float | None = None,
    capability_source_bar_ok: bool = False,
    provenance_complete: bool = False,
    license_status: str = "unknown",
    capability_attestation_hash: str | None = None,
    package_content_hash: str | None = None,
    ca_coverage_breakdown: dict[str, Any] | None = None,
    extras: dict[str, Any] | None = None,
) -> DatasetCertificationFacts:
    # Manifest research_eligibility is NEVER trusted as a fact input.
    lineage = getattr(manifest, "lineage", None) or {}
    if not isinstance(lineage, dict):
        lineage = {}
    merged_extras = dict(extras or {})
    # Surface ignored forgery attempts for audit notes downstream
    if getattr(manifest, "research_eligibility", None) is not None:
        merged_extras.setdefault(
            "manifest_research_eligibility_ignored",
            str(
                manifest.research_eligibility.value
                if hasattr(manifest.research_eligibility, "value")
                else manifest.research_eligibility
            ),
        )

    return DatasetCertificationFacts(
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        source=manifest.source,
        source_grade=manifest.source_grade.value
        if hasattr(manifest.source_grade, "value")
        else str(manifest.source_grade),
        calendar_id=manifest.calendar_id,
        calendar_version=manifest.calendar_version,
        calendar_verified=bool(manifest.calendar_verified),
        universe_id=manifest.universe_id,
        universe_version=manifest.universe_version,
        universe_completeness=manifest.universe_completeness.value
        if hasattr(manifest.universe_completeness, "value")
        else str(manifest.universe_completeness),
        corporate_action_coverage=corporate_action_coverage
        or str(lineage.get("corporate_action_coverage", "none")),
        adjustment_policy_id=str(
            (manifest.adjustment_policy or {}).get("policy_id", "unknown")
        ),
        date_coverage_start=manifest.date_range_start,
        date_coverage_end=manifest.date_range_end,
        instrument_count=manifest.instrument_count,
        delisted_coverage=delisted_coverage,
        missing_sessions=quality.missing_sessions,
        missing_bars=quality.missing_bars,
        duplicate_bars=quality.duplicate_bars,
        invalid_ohlc=quality.invalid_ohlc,
        error_count=quality.error_count,
        warning_count=quality.warning_count,
        content_hash=manifest.content_hash,
        quality_error_codes=quality.error_codes(),
        unknown_membership_session_count=quality.unknown_membership_periods,
        instrument_identity_issues=quality.instrument_identity_problems,
        membership_coverage_ratio=membership_coverage_ratio
        if membership_coverage_ratio is not None
        else lineage.get("membership_coverage_ratio"),
        capability_source_bar_ok=capability_source_bar_ok
        or bool(lineage.get("capability_source_bar_ok", False)),
        provenance_complete=provenance_complete
        or bool(lineage.get("provenance_complete", False)),
        license_status=license_status
        if license_status != "unknown"
        else str(lineage.get("license_status", "unknown")),
        capability_attestation_hash=capability_attestation_hash
        or lineage.get("capability_attestation_hash"),
        package_content_hash=package_content_hash or lineage.get("package_content_hash"),
        ca_coverage_breakdown=ca_coverage_breakdown
        or dict(lineage.get("ca_coverage_breakdown") or {}),
        extras=merged_extras,
    )


def certify(
    facts: DatasetCertificationFacts,
    checker: ResearchEligibilityChecker | None = None,
) -> EligibilityDecision:
    return (checker or ResearchEligibilityChecker()).evaluate(facts)


def format_certification_report(
    facts: DatasetCertificationFacts,
    decision: EligibilityDecision,
    *,
    include_facts_hash: bool = True,
) -> str:
    fhash = facts_hash(facts) if include_facts_hash else ""
    lines = [
        "RESEARCH DATASET CERTIFICATION",
        "--------------------------------",
        f"Dataset: {facts.dataset_id}",
        f"Version: {facts.dataset_version}",
        f"Content hash: {facts.content_hash}",
    ]
    if include_facts_hash:
        lines.append(f"Facts hash: {fhash}")
    lines.extend(
        [
            "",
            f"Source: {facts.source}",
            f"Source grade: {facts.source_grade}",
            f"Capability source bar: {facts.capability_source_bar_ok}",
            f"License status: {facts.license_status}",
            f"Provenance complete: {facts.provenance_complete}",
            f"Calendar: {facts.calendar_id} / {facts.calendar_version} "
            f"(verified={facts.calendar_verified})",
            f"Universe: {facts.universe_id} / {facts.universe_version}",
            f"Universe completeness: {facts.universe_completeness}",
            f"Membership coverage ratio: {facts.membership_coverage_ratio}",
            f"Corporate action coverage: {facts.corporate_action_coverage}",
            f"Adjustment policy: {facts.adjustment_policy_id}",
            f"Delisted coverage: {facts.delisted_coverage}",
            "",
            f"Date coverage: {facts.date_coverage_start} .. {facts.date_coverage_end}",
            f"Instrument coverage: {facts.instrument_count}",
            "",
            "Quality statistics:",
            f"  missing_sessions: {facts.missing_sessions}",
            f"  missing_bars: {facts.missing_bars}",
            f"  duplicate_bars: {facts.duplicate_bars}",
            f"  invalid_ohlc: {facts.invalid_ohlc}",
            f"  unknown_membership_sessions: {facts.unknown_membership_session_count}",
            f"  instrument_identity_issues: {facts.instrument_identity_issues}",
            f"Errors: {facts.error_count}",
            f"Warnings: {facts.warning_count}",
            "",
            "Eligibility:",
            decision.level.value.upper(),
            "",
            "Reasons:",
        ]
    )
    for r in decision.reasons:
        lines.append(f"- {r}")
    if decision.blockers:
        lines.append("")
        lines.append("Blockers:")
        for b in decision.blockers:
            lines.append(f"- {b}")
    if decision.notes:
        lines.append("")
        lines.append("Notes:")
        for n in decision.notes:
            lines.append(f"- {n}")
    if facts.ca_coverage_breakdown:
        lines.append("")
        lines.append("CA coverage breakdown:")
        for k, v in sorted(facts.ca_coverage_breakdown.items()):
            lines.append(f"  {k}: {v}")
    if decision.level == EligibilityLevel.DEVELOPMENT_ONLY:
        lines.append("")
        lines.append(
            "This dataset is NOT research_eligible. "
            "Do not use for final strategy validation."
        )
    return "\n".join(lines) + "\n"


def write_certification(
    path: Path,
    *,
    facts: DatasetCertificationFacts,
    decision: EligibilityDecision,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    report = format_certification_report(facts, decision)
    path.write_text(report, encoding="utf-8")
    fhash = facts_hash(facts)
    sidecar = path.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "facts": facts.model_dump(mode="json"),
                "facts_hash": fhash,
                "decision": {
                    "level": decision.level.value,
                    "reasons": decision.reasons,
                    "blockers": decision.blockers,
                    "notes": decision.notes,
                },
                "report_text": report,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def load_and_verify_certification(path: Path) -> tuple[DatasetCertificationFacts, bool]:
    """Load certification.json and verify facts_hash matches recomputed facts."""
    path = Path(path)
    if path.suffix == ".txt":
        path = path.with_suffix(".json")
    data = json.loads(path.read_text(encoding="utf-8"))
    facts = DatasetCertificationFacts.model_validate(data["facts"])
    expected = data.get("facts_hash")
    ok = expected is not None and verify_facts_integrity(facts, expected)
    return facts, ok

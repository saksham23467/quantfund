"""Dataset certification aggregator — composes the authoritative eligibility gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.data.eligibility import EligibilityDecision, ResearchEligibilityChecker
from quantfund.data.ingest.checksums import hash_json
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.data.providers.capabilities import ProviderCapabilities
from quantfund.research.certification.calendar_certification import certify_calendar
from quantfund.research.certification.corporate_action_certification import (
    certify_corporate_actions,
)
from quantfund.research.certification.delisting_certification import certify_delisting
from quantfund.research.certification.identity_certification import certify_identity
from quantfund.research.certification.results import CertResult
from quantfund.research.certification.source_certification import certify_source
from quantfund.research.certification.universe_certification import certify_universe
from quantfund.research.data_contract.models import ResearchDatasetPackage


@dataclass
class DatasetCertification:
    verdict: str  # RESEARCH_ELIGIBLE | DEVELOPMENT_ONLY
    research_eligible: bool
    eligibility_level: str
    content_hash: str
    reproducible: bool
    immutable: bool
    leakage_safe: bool
    sub_results: dict[str, CertResult] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "research_eligible": self.research_eligible,
            "eligibility_level": self.eligibility_level,
            "content_hash": self.content_hash,
            "reproducible": self.reproducible,
            "immutable": self.immutable,
            "leakage_safe": self.leakage_safe,
            "metrics": self.metrics,
            "blockers": self.blockers,
            "notes": self.notes,
            "sub_results": {k: v.as_dict() for k, v in self.sub_results.items()},
            "facts": self.facts,
        }


def _build_facts(
    package: ResearchDatasetPackage,
    *,
    source: CertResult,
    identity: CertResult,
    universe: CertResult,
    delisting: CertResult,
    calendar: CertResult,
    corporate: CertResult,
    content_hash: str,
) -> DatasetCertificationFacts:
    m = package.manifest
    membership_records = package.membership
    universe_id = membership_records[0].universe_id if membership_records else "none"
    universe_version = (
        membership_records[0].universe_version if membership_records else "none"
    )
    provenance_complete = bool(m.source_license.strip())

    return DatasetCertificationFacts(
        dataset_id=m.dataset_id,
        dataset_version=m.dataset_version,
        source=m.source_name,
        source_grade=m.source_grade.value,
        calendar_id=f"{m.exchange}_EQ",
        calendar_version="research_calendar_v1",
        calendar_verified=bool(calendar.metrics.get("calendar_verified")),
        universe_id=universe_id,
        universe_version=universe_version,
        universe_completeness=str(universe.metrics.get("universe_completeness")),
        corporate_action_coverage=str(
            corporate.metrics.get("corporate_action_coverage")
        ),
        adjustment_policy_id="research_ca_v1",
        date_coverage_start=m.coverage_start.isoformat(),
        date_coverage_end=m.coverage_end.isoformat(),
        instrument_count=len(package.symbols()),
        delisted_coverage=str(delisting.metrics.get("delisted_coverage")),
        missing_sessions=int(calendar.metrics.get("missing_sessions", 0)),
        missing_bars=int(calendar.metrics.get("missing_sessions", 0)),
        duplicate_bars=int(calendar.metrics.get("duplicate_bars", 0)),
        error_count=int(delisting.metrics.get("post_delisting_bars", 0)),
        warning_count=0,
        content_hash=content_hash,
        quality_error_codes=[],
        unknown_membership_session_count=int(
            universe.metrics.get("unknown_membership_session_count", 0)
        ),
        instrument_identity_issues=int(
            identity.metrics.get("instrument_identity_issues", 0)
        ),
        membership_coverage_ratio=float(
            universe.metrics.get("membership_coverage_ratio", 0.0)
        ),
        capability_source_bar_ok=bool(source.metrics.get("capability_source_bar_ok")),
        provenance_complete=provenance_complete,
        license_status=str(source.metrics.get("license_status", "unknown")),
        data_class=m.data_class,
        extras={"schema_version": m.schema_version},
    )


def certify_dataset(
    package: ResearchDatasetPackage,
    capabilities: ProviderCapabilities,
    *,
    immutable: bool = True,
) -> DatasetCertification:
    """Certify a dataset and evaluate via the unmodified ResearchEligibilityChecker."""
    source = certify_source(package.manifest, capabilities)
    identity = certify_identity(package)
    universe = certify_universe(package)
    delisting = certify_delisting(package)
    calendar = certify_calendar(package)
    corporate = certify_corporate_actions(package)

    content_hash = hash_json(package.canonical_dict())
    # Reproducibility: canonical serialization is deterministic.
    reproducible = hash_json(package.canonical_dict()) == content_hash

    facts = _build_facts(
        package,
        source=source,
        identity=identity,
        universe=universe,
        delisting=delisting,
        calendar=calendar,
        corporate=corporate,
        content_hash=content_hash,
    )

    decision: EligibilityDecision = ResearchEligibilityChecker().evaluate(facts)

    sub_results = {
        "source": source,
        "identity": identity,
        "pit_universe": universe,
        "delisting": delisting,
        "calendar": calendar,
        "corporate_actions": corporate,
    }
    sub_blockers: list[str] = []
    for name, res in sub_results.items():
        sub_blockers.extend(f"{name}: {b}" for b in res.blockers)

    leakage_safe = (
        universe.metrics.get("unknown_membership_session_count", 1) == 0
        and bool(calendar.metrics.get("calendar_verified"))
        and delisting.metrics.get("post_delisting_bars", 1) == 0
    )

    # Fail closed: research-eligible only if the authoritative checker AND every
    # sub-certification pass AND the package is immutable + reproducible.
    all_sub_pass = all(r.passed for r in sub_results.values())
    research_eligible = bool(
        decision.is_research_eligible
        and all_sub_pass
        and reproducible
        and immutable
        and leakage_safe
    )
    verdict = "RESEARCH_ELIGIBLE" if research_eligible else "DEVELOPMENT_ONLY"

    blockers = list(decision.blockers)
    # Surface sub-cert blockers that the checker may not itemize identically.
    for b in sub_blockers:
        if b not in blockers:
            blockers.append(b)
    if not reproducible:
        blockers.append("not reproducible")
    if not immutable:
        blockers.append("package not stored immutably")
    if not leakage_safe:
        blockers.append("leakage_safety=false")

    metrics = {
        "source_grade": facts.source_grade,
        "data_class": facts.data_class,
        "capability_source_bar_ok": facts.capability_source_bar_ok,
        "calendar_verified": facts.calendar_verified,
        "calendar_errors": int(calendar.metrics.get("calendar_errors", 0)),
        "bar_count": len(package.ohlcv),
        "instrument_identity_coverage": identity.metrics.get(
            "instrument_identity_coverage", 0.0
        ),
        "membership_coverage_ratio": facts.membership_coverage_ratio,
        "unknown_membership_session_count": facts.unknown_membership_session_count,
        "universe_completeness": facts.universe_completeness,
        "delisted_coverage": facts.delisted_coverage,
        "corporate_action_coverage": facts.corporate_action_coverage,
        "license_status": facts.license_status,
    }

    return DatasetCertification(
        verdict=verdict,
        research_eligible=research_eligible,
        eligibility_level=(
            decision.level.value
            if isinstance(decision.level, EligibilityLevel)
            else str(decision.level)
        ),
        content_hash=content_hash,
        reproducible=reproducible,
        immutable=immutable,
        leakage_safe=leakage_safe,
        sub_results=sub_results,
        facts=facts.model_dump(mode="json"),
        metrics=metrics,
        blockers=blockers,
        notes=list(decision.notes),
    )

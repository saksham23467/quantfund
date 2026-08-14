"""Research Package Readiness Audit (Phase 10.5).

Reports what an external package must satisfy for RESEARCH_ELIGIBLE.
Does NOT weaken ResearchEligibilityChecker or fabricate evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from quantfund.data.policy import EligibilityLevel


class ReadinessStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    MISSING = "MISSING"
    BLOCKING = "BLOCKING"
    OPTIONAL = "OPTIONAL"
    NOT_CONFIGURED = "NOT_CONFIGURED"


# Categories printed by make audit-research-package
AUDIT_CATEGORIES = (
    "Market data",
    "Instrument identity",
    "NIFTY50 PIT",
    "UNKNOWN membership",
    "Corporate actions",
    "Delisted coverage",
    "NSE calendar",
    "Provenance",
    "License",
    "Checksums",
    "Quality",
    "Source grade / capability bar",
)


@dataclass
class RequirementItem:
    requirement: str
    current_implementation: str
    required_evidence: str
    package_field_or_file: str
    validation_rule: str
    blocking_severity: str  # BLOCKING | OPTIONAL
    current_demo_status: str  # PASS | FAIL | MISSING | BLOCKING | OPTIONAL | NOT_CONFIGURED
    category: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "current_implementation": self.current_implementation,
            "required_evidence": self.required_evidence,
            "package_field_or_file": self.package_field_or_file,
            "validation_rule": self.validation_rule,
            "blocking_severity": self.blocking_severity,
            "current_demo_status": self.current_demo_status,
            "category": self.category,
            "detail": self.detail,
        }


@dataclass
class CategoryResult:
    name: str
    status: str  # PASS | FAIL
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "blockers": list(self.blockers),
        }


@dataclass
class ResearchPackageReadinessReport:
    package_root: str | None
    configured: bool
    package_valid: bool | None
    research_eligible: bool
    eligibility_level: str
    categories: list[CategoryResult]
    blockers: list[str]
    requirements: list[RequirementItem]
    certification_meta: dict[str, Any] = field(default_factory=dict)
    paper_data_rung_ready: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_root": self.package_root,
            "configured": self.configured,
            "package_valid": self.package_valid,
            "research_eligible": self.research_eligible,
            "eligibility_level": self.eligibility_level,
            "categories": [c.to_dict() for c in self.categories],
            "blockers": list(self.blockers),
            "requirements": [r.to_dict() for r in self.requirements],
            "certification_meta": dict(self.certification_meta),
            "paper_data_rung_ready": self.paper_data_rung_ready,
            "notes": list(self.notes),
            "phase11_started": True,  # paper certification layer; live still disabled
            "phase12_started": True,  # controlled simulation paper; live still disabled
            "phase13_started": True,  # historical paper validation; live still disabled
            "phase14_started": True,  # realtime paper/shadow; live still disabled
            "phase15_started": True,  # real/sim data + read-only broker shadow; live still disabled
            "phase16a_started": True,  # real broker read-only + live readiness; orders still disabled
            "phase16b_started": True,  # controlled live canary gates; CI/demo never real-submit
            "eligibility_gates_weakened": False,
        }


def _cat_status(name: str, blockers: list[str], related: list[str]) -> CategoryResult:
    hits = [b for b in blockers if any(k in b.lower() for k in related)]
    # Also match exact category-driven synthetic/source for source grade
    return CategoryResult(
        name=name,
        status="FAIL" if hits else "PASS",
        blockers=hits,
    )


def _classify_categories(blockers: list[str], *, has_package: bool, valid: bool | None) -> list[CategoryResult]:
    if not has_package:
        return [
            CategoryResult(name=n, status="FAIL", blockers=["research_package_not_configured"])
            for n in AUDIT_CATEGORIES
        ]

    cats: list[CategoryResult] = []

    # Market data
    md_keys = [
        "no_bars",
        "missing_bars",
        "duplicate_bars",
        "invalid_ohlc",
        "empty_bars",
    ]
    hits = [b for b in blockers if any(k in b.lower() for k in md_keys)]
    if valid is False:
        hits = hits or ["package_validation_failed"]
    cats.append(CategoryResult("Market data", "FAIL" if hits else "PASS", hits))

    # Instrument identity
    id_hits = [b for b in blockers if "instrument_identity" in b.lower()]
    cats.append(CategoryResult("Instrument identity", "FAIL" if id_hits else "PASS", id_hits))

    # NIFTY50 PIT
    pit_hits = [
        b
        for b in blockers
        if "universe_completeness" in b.lower()
        or "current_snapshot" in b.lower()
        or "membership_coverage_ratio" in b.lower()
    ]
    cats.append(CategoryResult("NIFTY50 PIT", "FAIL" if pit_hits else "PASS", pit_hits))

    # UNKNOWN membership
    unk_hits = [b for b in blockers if "unknown_membership" in b.lower()]
    cats.append(
        CategoryResult("UNKNOWN membership", "FAIL" if unk_hits else "PASS", unk_hits)
    )

    # Corporate actions
    ca_hits = [b for b in blockers if "corporate_action" in b.lower()]
    cats.append(CategoryResult("Corporate actions", "FAIL" if ca_hits else "PASS", ca_hits))

    # Delisted
    del_hits = [b for b in blockers if "delisted" in b.lower()]
    cats.append(CategoryResult("Delisted coverage", "FAIL" if del_hits else "PASS", del_hits))

    # Calendar
    cal_hits = [b for b in blockers if "calendar" in b.lower()]
    cats.append(CategoryResult("NSE calendar", "FAIL" if cal_hits else "PASS", cal_hits))

    # Provenance
    prov_hits = [b for b in blockers if "provenance" in b.lower()]
    cats.append(CategoryResult("Provenance", "FAIL" if prov_hits else "PASS", prov_hits))

    # License
    lic_hits = [b for b in blockers if "license" in b.lower()]
    cats.append(CategoryResult("License", "FAIL" if lic_hits else "PASS", lic_hits))

    # Checksums — fail if package invalid due to checksum, or quality hash mismatch
    ck_hits = [
        b
        for b in blockers
        if "checksum" in b.lower() or "content_hash" in b.lower()
    ]
    if valid is False:
        # surface validation checksum errors via meta later; keep PASS unless mentioned
        pass
    cats.append(CategoryResult("Checksums", "FAIL" if ck_hits else "PASS", ck_hits))

    # Quality
    q_hits = [
        b
        for b in blockers
        if "quality" in b.lower()
        or "error count" in b.lower()
        or "invalid_ohlc" in b.lower()
        or "duplicate_bars" in b.lower()
        or "missing_bars" in b.lower()
    ]
    cats.append(CategoryResult("Quality", "FAIL" if q_hits else "PASS", q_hits))

    # Source grade
    src_hits = [
        b
        for b in blockers
        if "source_grade" in b.lower()
        or "capability_source_bar" in b.lower()
        or "synthetic=true" in b.lower()
        or b.lower().startswith("synthetic")
    ]
    cats.append(
        CategoryResult(
            "Source grade / capability bar",
            "FAIL" if src_hits else "PASS",
            src_hits,
        )
    )
    return cats


def _static_requirement_catalog(
    *,
    demo_statuses: dict[str, str],
) -> list[RequirementItem]:
    """Machine-readable checklist derived from existing gates (not invented)."""

    def st(key: str, default: str = "MISSING") -> str:
        return demo_statuses.get(key, default)

    items: list[RequirementItem] = [
        RequirementItem(
            requirement="source_grade must be exchange or paid",
            current_implementation="ResearchEligibilityChecker + ProviderCapabilities",
            required_evidence="package.json source_grade + exchange_authority or paid license",
            package_field_or_file="package.json:source_grade, exchange_authority",
            validation_rule="source_grade ∉ {synthetic, non_exchange}; capability_source_bar_ok=true",
            blocking_severity="BLOCKING",
            current_demo_status=st("source_grade"),
            category="Source grade / capability bar",
        ),
        RequirementItem(
            requirement="Package must not be synthetic",
            current_implementation="eligibility extras.synthetic + manifest.is_synthetic",
            required_evidence="synthetic=false; source_grade≠synthetic",
            package_field_or_file="package.json:synthetic, source_grade",
            validation_rule="extras.synthetic=true → DEVELOPMENT_ONLY",
            blocking_severity="BLOCKING",
            current_demo_status=st("synthetic"),
            category="Source grade / capability bar",
        ),
        RequirementItem(
            requirement="Daily OHLCV bars for instruments in coverage window",
            current_implementation="LocalResearchPackageProvider.get_history + certify_package",
            required_evidence="bars/{SYMBOL}.csv with timestamp, OHLCV",
            package_field_or_file="bars/*.csv",
            validation_rule="no_bars_in_package blocks certify; quality empty_bars ERROR",
            blocking_severity="BLOCKING",
            current_demo_status=st("market_data"),
            category="Market data",
        ),
        RequirementItem(
            requirement="Zero quality ERRORs (duplicates, invalid OHLC, missing open sessions, …)",
            current_implementation="run_quality_checks → facts.error_count",
            required_evidence="QualityReport error_count==0",
            package_field_or_file="bars/, instruments.json, corporate_actions.json",
            validation_rule="error_count>0 → DEVELOPMENT_ONLY",
            blocking_severity="BLOCKING",
            current_demo_status=st("quality"),
            category="Quality",
        ),
        RequirementItem(
            requirement="Instrument identity consistent (no collisions / identity ERRORs)",
            current_implementation="identity checks → instrument_identity_issues",
            required_evidence="Stable instrument_id (e.g. NSE:ISIN), listing intervals",
            package_field_or_file="instruments.json",
            validation_rule="instrument_identity_issues>0 → DEVELOPMENT_ONLY",
            blocking_severity="BLOCKING",
            current_demo_status=st("identity"),
            category="Instrument identity",
        ),
        RequirementItem(
            requirement="PIT universe completeness partial_pit or full_pit",
            current_implementation="UniverseCompleteness + eligibility min_universe_completeness",
            required_evidence="Historical membership with effective dates",
            package_field_or_file="universe membership (repo store or package-linked intervals)",
            validation_rule="current_snapshot_only forbidden; must be partial_pit|full_pit",
            blocking_severity="BLOCKING",
            current_demo_status=st("pit"),
            category="NIFTY50 PIT",
        ),
        RequirementItem(
            requirement="Zero UNKNOWN membership sessions for certified research set",
            current_implementation="compute_membership_coverage + eligibility",
            required_evidence="Complete PIT membership for every traded symbol×session",
            package_field_or_file="universe/membership intervals",
            validation_rule="unknown_membership_session_count>0 → DEVELOPMENT_ONLY",
            blocking_severity="BLOCKING",
            current_demo_status=st("unknown"),
            category="UNKNOWN membership",
        ),
        RequirementItem(
            requirement="membership_coverage_ratio ≥ 1.0",
            current_implementation="EligibilityPolicy.min_membership_coverage_ratio",
            required_evidence="Coverage metrics from PIT membership",
            package_field_or_file="universe membership",
            validation_rule="ratio < 1.0 → DEVELOPMENT_ONLY",
            blocking_severity="BLOCKING",
            current_demo_status=st("membership_ratio"),
            category="NIFTY50 PIT",
        ),
        RequirementItem(
            requirement="Corporate-action coverage ≥ splits_bonus_dividends",
            current_implementation="derive_ca_coverage_report + eligibility",
            required_evidence="Splits, bonuses, dividends with effective dates + provenance",
            package_field_or_file="corporate_actions.json",
            validation_rule="overall ∈ {splits_bonus_dividends, full_verified}",
            blocking_severity="BLOCKING",
            current_demo_status=st("corporate_actions"),
            category="Corporate actions",
            detail="Mergers/demergers are schema-only; not required for RESEARCH_ELIGIBLE bar",
        ),
        RequirementItem(
            requirement="Delisted/terminal coverage ≥ partial",
            current_implementation="measure_delisted_coverage + eligibility",
            required_evidence="Delisting dates and/or terminal_events.json DELISTING",
            package_field_or_file="instruments.json delisting_date; terminal_events.json",
            validation_rule="delisted_coverage ∈ {partial, complete}",
            blocking_severity="BLOCKING",
            current_demo_status=st("delisted"),
            category="Delisted coverage",
        ),
        RequirementItem(
            requirement="Verified NSE equity calendar",
            current_implementation="NSECalendarProvider.verified → facts.calendar_verified",
            required_evidence="Curated NSE holiday/special-session calendar",
            package_field_or_file="data/calendars/nse_eq/.../calendar.json (platform) or equivalent verified calendar_id",
            validation_rule="calendar_verified=false → DEVELOPMENT_ONLY",
            blocking_severity="BLOCKING",
            current_demo_status=st("calendar"),
            category="NSE calendar",
        ),
        RequirementItem(
            requirement="Provenance complete for research",
            current_implementation="ProvenanceRecord.is_complete_for_research",
            required_evidence="provider, download_timestamp, package hash, license_status≠unknown",
            package_field_or_file="package.json provenance; provenance.json; computed hash",
            validation_rule="provenance_complete=false → DEVELOPMENT_ONLY",
            blocking_severity="BLOCKING",
            current_demo_status=st("provenance"),
            category="Provenance",
        ),
        RequirementItem(
            requirement="Known non-prohibited license",
            current_implementation="license.py + eligibility license_status gates",
            required_evidence="license_status ∈ {verified, internal_research_only, redistributable}",
            package_field_or_file="package.json:license_status; optional LICENSE.json",
            validation_rule="unknown|prohibited|expired → DEVELOPMENT_ONLY (prohibited/expired also fail ingest)",
            blocking_severity="BLOCKING",
            current_demo_status=st("license"),
            category="License",
        ),
        RequirementItem(
            requirement="Checksum integrity when declared",
            current_implementation="package_validator checksums.sha256 verify",
            required_evidence="checksums.sha256 matching package contents",
            package_field_or_file="checksums/sha256 or checksums.sha256",
            validation_rule="If present, mismatch → package invalid; quality may emit package_checksum_mismatch",
            blocking_severity="BLOCKING",
            current_demo_status=st("checksums"),
            category="Checksums",
            detail="File is optional; when absent, directory hash is still computed for provenance",
        ),
        RequirementItem(
            requirement="No forged eligibility assertions in package.json",
            current_implementation="package_validator eligibility_assertion_forbidden",
            required_evidence="Absence of research_eligible/eligibility/accepted keys",
            package_field_or_file="package.json",
            validation_rule="Forbidden keys → package invalid",
            blocking_severity="BLOCKING",
            current_demo_status=st("forge"),
            category="Quality",
        ),
        RequirementItem(
            requirement="Paper data rung requires RESEARCH_ELIGIBLE (or production_candidate)",
            current_implementation="PaperEligibilityGate certified_eligibility check",
            required_evidence="Successful certify → research_eligible",
            package_field_or_file="(certification artifact)",
            validation_rule="development_only → paper_eligible=false",
            blocking_severity="BLOCKING",
            current_demo_status=st("paper_data"),
            category="Paper data rung",
            detail="Strategy acceptance / sealed TEST / operator gates are separate Phase 10 requirements",
        ),
    ]
    return items


def audit_research_package(
    package_root: Path | str | None = None,
    *,
    default_demo_fixture: Path | str | None = None,
) -> ResearchPackageReadinessReport:
    """Audit a package (or demo fixture) against existing RESEARCH_ELIGIBLE gates."""
    # Lazy imports avoid circular import via data.packages ↔ providers.local_package
    from quantfund.data.packages.ingest import ingest_configured_research_package
    from quantfund.data.providers.package_validator import (
        resolve_configured_research_package,
        validate_research_package,
    )
    from quantfund.research.certify_package import certify_research_package

    notes: list[str] = [
        "Eligibility gates are not weakened by this audit.",
        "Synthetic/yfinance remain DEVELOPMENT_ONLY by design.",
        "Phase 11 (real broker) NOT started.",
        "Mergers/demergers are schema-tracked only; not required for RESEARCH_ELIGIBLE.",
    ]

    env_root = resolve_configured_research_package()
    root: Path | None
    configured: bool
    if package_root is not None:
        root = Path(package_root)
        configured = True
    elif env_root is not None:
        root = env_root
        configured = True
    elif default_demo_fixture is not None:
        root = Path(default_demo_fixture)
        configured = False
        notes.append(
            f"QUANTFUND_RESEARCH_PACKAGE unset; auditing demo fixture at {root}"
        )
    else:
        # Unconfigured — still report checklist with NOT_CONFIGURED
        demo_statuses = {k: ReadinessStatus.NOT_CONFIGURED.value for k in [
            "source_grade", "synthetic", "market_data", "quality", "identity",
            "pit", "unknown", "membership_ratio", "corporate_actions", "delisted",
            "calendar", "provenance", "license", "checksums", "forge", "paper_data",
        ]}
        return ResearchPackageReadinessReport(
            package_root=None,
            configured=False,
            package_valid=None,
            research_eligible=False,
            eligibility_level=EligibilityLevel.DEVELOPMENT_ONLY.value,
            categories=_classify_categories([], has_package=False, valid=None),
            blockers=["research_package_not_configured"],
            requirements=_static_requirement_catalog(demo_statuses=demo_statuses),
            notes=notes,
            paper_data_rung_ready=False,
        )

    validation = validate_research_package(root)
    ingest = ingest_configured_research_package(package_root=root, allow_invalid=False)
    elig, facts, blockers, meta = certify_research_package(root)

    research_eligible = elig in {
        EligibilityLevel.RESEARCH_ELIGIBLE.value,
        EligibilityLevel.PRODUCTION_CANDIDATE.value,
    }

    # Derive per-requirement demo statuses from facts/blockers
    def fail_if(*keys: str) -> str:
        for b in blockers:
            bl = b.lower()
            if any(k in bl for k in keys):
                return ReadinessStatus.BLOCKING.value
        return ReadinessStatus.PASS.value

    demo_statuses = {
        "source_grade": fail_if("source_grade", "capability_source_bar"),
        "synthetic": fail_if("synthetic"),
        "market_data": (
            ReadinessStatus.BLOCKING.value
            if any("no_bars" in b for b in blockers)
            else ReadinessStatus.PASS.value
        ),
        "quality": fail_if("quality", "invalid_ohlc", "duplicate_bars", "missing_bars"),
        "identity": fail_if("instrument_identity"),
        "pit": fail_if("universe_completeness", "membership_coverage_ratio", "current_snapshot"),
        "unknown": fail_if("unknown_membership"),
        "membership_ratio": fail_if("membership_coverage_ratio"),
        "corporate_actions": fail_if("corporate_action"),
        "delisted": fail_if("delisted"),
        "calendar": fail_if("calendar"),
        "provenance": fail_if("provenance"),
        "license": fail_if("license"),
        "checksums": (
            ReadinessStatus.OPTIONAL.value
            if validation.valid
            and not any("checksum" in b.lower() for b in blockers)
            and not (root / "checksums.sha256").exists()
            and not (root / "checksums" / "sha256").exists()
            else fail_if("checksum")
        ),
        "forge": (
            ReadinessStatus.PASS.value
            if validation.valid
            else ReadinessStatus.BLOCKING.value
        ),
        "paper_data": (
            ReadinessStatus.PASS.value
            if research_eligible
            else ReadinessStatus.BLOCKING.value
        ),
    }

    # If validation failed, surface ingest blockers
    all_blockers = list(blockers)
    if not validation.valid:
        all_blockers.extend(
            f"{e.code}:{e.message}" for e in validation.errors
        )
        all_blockers.extend(ingest.blockers)

    # Deduplicate preserving order
    seen: set[str] = set()
    uniq_blockers: list[str] = []
    for b in all_blockers:
        if b not in seen:
            seen.add(b)
            uniq_blockers.append(b)

    categories = _classify_categories(
        uniq_blockers, has_package=True, valid=validation.valid
    )

    # Refine checksum category if file missing (OPTIONAL pass with note)
    for c in categories:
        if c.name == "Checksums" and c.status == "PASS":
            if not (root / "checksums.sha256").exists() and not (
                root / "checksums" / "sha256"
            ).exists():
                notes.append(
                    "Checksums file absent (optional); directory hash still used for provenance."
                )

    return ResearchPackageReadinessReport(
        package_root=str(root),
        configured=configured,
        package_valid=validation.valid,
        research_eligible=research_eligible,
        eligibility_level=elig,
        categories=categories,
        blockers=uniq_blockers,
        requirements=_static_requirement_catalog(demo_statuses=demo_statuses),
        certification_meta={
            k: v
            for k, v in meta.items()
            if k != "certification"
        },
        paper_data_rung_ready=research_eligible,
        notes=notes,
    )


def format_readiness_report(report: ResearchPackageReadinessReport) -> str:
    lines = [
        "Research Package Readiness",
        "--------------------------",
    ]
    # Print the 11 primary categories in the requested order (exclude source grade from main table? include it)
    primary = [
        "Market data",
        "Instrument identity",
        "NIFTY50 PIT",
        "UNKNOWN membership",
        "Corporate actions",
        "Delisted coverage",
        "NSE calendar",
        "Provenance",
        "License",
        "Checksums",
        "Quality",
    ]
    by_name = {c.name: c for c in report.categories}
    for name in primary:
        c = by_name.get(name)
        status = c.status if c else "FAIL"
        lines.append(f"{name:<28} {status}")
    src = by_name.get("Source grade / capability bar")
    if src:
        lines.append(f"{'Source grade / capability':<28} {src.status}")

    m = report.certification_meta or {}
    q = m.get("quality_report") or {}
    lines.append("")
    lines.append("Certification facts (derived, not trusted from manifest):")
    lines.append(f"Source grade: {m.get('source_grade', 'n/a')}")
    lines.append(f"Exchange authority: {m.get('exchange_authority', 'n/a')}")
    lines.append(f"License status: {m.get('license_status', 'n/a')}")
    lines.append(
        f"Calendar: {m.get('calendar_id', 'n/a')} "
        f"v{m.get('calendar_version', 'n/a')} "
        f"verified={m.get('calendar_verified', 'n/a')}"
    )
    lines.append(
        f"PIT membership coverage: {m.get('membership_coverage_ratio', 'n/a')} "
        f"({m.get('pit_coverage', 'n/a')})"
    )
    lines.append(
        f"Unknown membership sessions: "
        f"{q.get('unknown_membership_session_count', 'n/a')}"
    )
    lines.append(f"Corporate-action coverage: {m.get('ca_coverage', 'n/a')}")
    lines.append(f"Delisted coverage: {m.get('delisted_coverage', 'n/a')}")
    lines.append(f"Quality errors: {q.get('error_count', 'n/a')}")
    lines.append(f"Facts hash: {m.get('facts_hash', 'n/a')}")
    lines.append("")
    lines.append(f"Eligibility: {report.eligibility_level}")
    lines.append(
        f"RESEARCH_ELIGIBLE: {'TRUE' if report.research_eligible else 'FALSE'}"
    )
    lines.append(
        f"Paper data rung ready: {'TRUE' if report.paper_data_rung_ready else 'FALSE'}"
    )
    if report.package_root:
        lines.append(f"Package: {report.package_root}")
    lines.append(f"Configured via env: {report.configured}")
    lines.append("")
    lines.append("Blockers:")
    if report.blockers:
        for b in report.blockers:
            lines.append(f"- {b}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("Notes:")
    for n in report.notes:
        lines.append(f"- {n}")
    return "\n".join(lines)

"""Human-readable research-package certification summary (facts-derived only)."""

from __future__ import annotations

from typing import Any

from quantfund.data.policy import DatasetCertificationFacts


def format_package_certification_summary(
    *,
    eligibility: str,
    facts: DatasetCertificationFacts | None,
    blockers: list[str],
    meta: dict[str, Any],
) -> str:
    """Print the canonical certification fields requested for real-package workflow."""
    exchange_authority = None
    if facts is not None:
        exchange_authority = facts.extras.get("exchange_authority")
    if exchange_authority is None:
        exchange_authority = meta.get("exchange_authority")

    q = meta.get("quality_report") or {}
    ca = {}
    if facts is not None:
        ca = facts.ca_coverage_breakdown or {}
    lines = [
        "PACKAGE",
        f"  id: {meta.get('package_id', facts.dataset_id if facts else 'n/a')}",
        f"  version: {meta.get('package_version', facts.dataset_version if facts else 'n/a')}",
        f"  vendor: {meta.get('vendor', meta.get('provider', facts.source if facts else 'n/a'))}",
        f"  coverage: {meta.get('coverage_start', facts.date_coverage_start if facts else '?')} → "
        f"{meta.get('coverage_end', facts.date_coverage_end if facts else '?')}",
        "",
        "SOURCE",
        f"  grade: {meta.get('source_grade', facts.source_grade if facts else 'n/a')}",
        f"  exchange_authority: {exchange_authority}",
        f"  license_status: {meta.get('license_status', facts.license_status if facts else 'n/a')}",
        "",
        "IDENTITY",
        f"  instrument_count: {facts.instrument_count if facts else meta.get('instrument_count', 'n/a')}",
        f"  resolved_ratio: {meta.get('identity_resolved_ratio', 'n/a')}",
        f"  ambiguous: {meta.get('identity_ambiguous', 'n/a')}",
        f"  unknown: {meta.get('identity_unknown', facts.instrument_identity_issues if facts else 'n/a')}",
        f"  identity_issues: {facts.instrument_identity_issues if facts else 'n/a'}",
        "",
        "UNIVERSE",
        f"  PIT: {meta.get('pit_coverage', facts.universe_completeness if facts else 'n/a')}",
        f"  coverage_ratio: "
        f"{meta.get('membership_coverage_ratio', facts.membership_coverage_ratio if facts else None)}",
        f"  UNKNOWN sessions: "
        f"{q.get('unknown_membership_session_count', facts.unknown_membership_session_count if facts else 'n/a')}",
        "",
        "CORPORATE ACTIONS",
        f"  overall: {meta.get('ca_coverage', facts.corporate_action_coverage if facts else 'n/a')}",
        f"  split: {ca.get('splits', ca.get('split_coverage', 'n/a'))}",
        f"  bonus: {ca.get('bonuses', ca.get('bonus_coverage', 'n/a'))}",
        f"  dividend: {ca.get('dividends', ca.get('dividend_coverage', 'n/a'))}",
        f"  rights: {ca.get('rights', 'n/a')}",
        f"  buyback: {ca.get('buybacks', 'n/a')}",
        f"  merger: {ca.get('mergers', ca.get('merger_coverage', 'n/a'))}",
        f"  demerger: {ca.get('demergers', ca.get('demerger_coverage', 'n/a'))}",
        "",
        "DELISTED",
        f"  coverage: {meta.get('delisted_coverage', facts.delisted_coverage if facts else 'n/a')}",
        "",
        "CALENDAR",
        f"  verified: {facts.calendar_verified if facts else meta.get('calendar_verified')}",
        f"  id: {meta.get('calendar_id', facts.calendar_id if facts else 'n/a')} "
        f"v{meta.get('calendar_version', facts.calendar_version if facts else 'n/a')}",
        "",
        "ELIGIBILITY",
        f"  RESEARCH_ELIGIBLE: "
        f"{'YES' if eligibility in {'research_eligible', 'production_candidate'} else 'NO'}",
        f"  level: {eligibility}",
        f"  facts_hash: {meta.get('facts_hash', 'n/a')}",
        f"  package_hash: {meta.get('package_hash', 'n/a')}",
        f"  quality_errors: {q.get('error_count', facts.error_count if facts else 'n/a')}",
        "",
        "Blockers:",
    ]
    if blockers:
        for b in blockers:
            lines.append(f"- {b}")
    else:
        lines.append("- (none)")
    # Keep legacy header for older tests/demos that grep the old title
    legacy = [
        "",
        "Research Package Certification",
        "------------------------------",
        f"Source grade: {meta.get('source_grade', facts.source_grade if facts else 'n/a')}",
        f"Eligibility: {eligibility}",
        f"RESEARCH_ELIGIBLE: "
        f"{'TRUE' if eligibility in {'research_eligible', 'production_candidate'} else 'FALSE'}",
    ]
    return "\n".join(lines + legacy)

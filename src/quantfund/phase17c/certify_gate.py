"""Eligibility dry-run via existing ResearchEligibilityChecker — no shortcuts."""

from __future__ import annotations

from typing import Any

from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel


def build_zerodha_cert_facts(
    *,
    dataset_id: str,
    dataset_version: str,
    content_hash: str,
    calendar_version: str,
    calendar_verified: bool,
    date_coverage_start: str,
    date_coverage_end: str,
    error_count: int,
    warning_count: int = 0,
    missing_sessions: int = 0,
    ca_coverage: str,
    universe_completeness: str,
    unknown_membership_session_count: int,
    membership_coverage_ratio: float,
    instrument_identity_issues: int,
    provenance_complete: bool = True,
    quality_error_codes: list[str] | None = None,
) -> DatasetCertificationFacts:
    """Honest facts for Zerodha historical packages.

    Source grade remains non_exchange / DEVELOPMENT_DATA — never forged.
    """
    return DatasetCertificationFacts(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        source="zerodha_historical_api",
        source_grade="non_exchange",
        calendar_id="NSE_EQ",
        calendar_version=calendar_version,
        calendar_verified=calendar_verified,
        universe_id="zerodha_broker_watchlist",
        universe_version="none",
        universe_completeness=universe_completeness,
        corporate_action_coverage=ca_coverage,
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start=date_coverage_start,
        date_coverage_end=date_coverage_end,
        instrument_count=1,
        delisted_coverage="unknown",
        missing_sessions=missing_sessions,
        error_count=error_count,
        warning_count=warning_count,
        content_hash=content_hash,
        quality_error_codes=list(quality_error_codes or []),
        unknown_membership_session_count=unknown_membership_session_count,
        instrument_identity_issues=instrument_identity_issues,
        membership_coverage_ratio=membership_coverage_ratio,
        capability_source_bar_ok=False,
        provenance_complete=provenance_complete,
        license_status="broker_account_restricted",
        data_class="DEVELOPMENT_DATA",
        extras={
            "provider": "zerodha",
            "phase": "17C",
            "research_eligible": False,  # ignored; derived only from facts
        },
    )


def evaluate_eligibility(facts: DatasetCertificationFacts) -> dict[str, Any]:
    decision = ResearchEligibilityChecker().evaluate(facts)
    return {
        "level": decision.level.value
        if isinstance(decision.level, EligibilityLevel)
        else str(decision.level),
        "is_research_eligible": decision.is_research_eligible,
        "blockers": list(decision.blockers),
        "reasons": list(decision.reasons),
        "notes": list(decision.notes),
        "zerodha_shortcut": False,
        "statement": (
            "Eligibility derived from DatasetCertificationFacts only. "
            "No Zerodha-specific shortcut applied."
        ),
    }

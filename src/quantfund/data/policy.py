"""Data quality and dataset eligibility policies (Phase 3 / Phase 5)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EligibilityLevel(str, Enum):
    """Phase 3 eligibility vocabulary (canonical)."""

    DEVELOPMENT_ONLY = "development_only"
    RESEARCH_ELIGIBLE = "research_eligible"
    PRODUCTION_CANDIDATE = "production_candidate"


class CorporateActionCoverage(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    SPLITS_BONUS_DIVIDENDS = "splits_bonus_dividends"
    FULL_VERIFIED = "full_verified"


class DelistedCoverage(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    COMPLETE = "complete"
    UNKNOWN = "unknown"


class DataQualityPolicy(BaseModel):
    """Mandatory ERROR conditions that block research eligibility."""

    model_config = ConfigDict(frozen=True)

    policy_id: str = "data_quality_policy_v1"
    fail_on_duplicate_bars: bool = True
    fail_on_invalid_ohlc: bool = True
    fail_on_missing_open_session: bool = True
    fail_on_negative_prices: bool = True
    fail_on_negative_volume: bool = True
    fail_on_timestamp_disorder: bool = True
    fail_on_raw_mutation: bool = True
    fail_on_post_delisting_bars: bool = True
    fail_on_bar_on_closed_session: bool = True
    warn_on_zero_volume: bool = True
    warn_on_stale_prices: bool = True
    warn_on_unknown_membership_periods: bool = True
    max_stale_sessions: int = 5


class DatasetEligibilityPolicy(BaseModel):
    """Rules for development_only / research_eligible / production_candidate.

    Phase 5 tightens explicitness; gates are never weaker than Phase 3.
    """

    model_config = ConfigDict(frozen=True)

    policy_id: str = "dataset_eligibility_policy_v1"
    require_calendar_verified: bool = True
    require_non_development_source: bool = True  # reject non_exchange/synthetic
    min_universe_completeness: list[str] = Field(
        default_factory=lambda: ["partial_pit", "full_pit"]
    )
    min_corporate_action_coverage: list[str] = Field(
        default_factory=lambda: ["splits_bonus_dividends", "full_verified"]
    )
    allow_unknown_membership_periods_for_research: bool = False
    min_membership_coverage_ratio: float = 1.0
    min_delisted_coverage_for_research: list[str] = Field(
        default_factory=lambda: ["partial", "complete"]
    )
    require_capability_source_bar: bool = True
    require_provenance_complete: bool = True
    require_license_not_prohibited: bool = True
    allow_unknown_license_for_research: bool = False
    production_requires_full_pit: bool = True
    production_requires_full_verified_ca: bool = True
    production_requires_delisted_coverage: list[str] = Field(
        default_factory=lambda: ["complete"]
    )
    production_requires_zero_quality_warnings: bool = False  # warnings OK; errors not


DEFAULT_QUALITY_POLICY = DataQualityPolicy()
DEFAULT_ELIGIBILITY_POLICY = DatasetEligibilityPolicy()


class DatasetCertificationFacts(BaseModel):
    """Explicit facts evaluated by ResearchEligibilityChecker."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    dataset_version: str
    source: str
    source_grade: str
    calendar_id: str
    calendar_version: str
    calendar_verified: bool
    universe_id: str
    universe_version: str
    universe_completeness: str
    corporate_action_coverage: str
    adjustment_policy_id: str
    date_coverage_start: str
    date_coverage_end: str
    instrument_count: int
    delisted_coverage: str = DelistedCoverage.UNKNOWN.value
    missing_sessions: int = 0
    missing_bars: int = 0
    duplicate_bars: int = 0
    invalid_ohlc: int = 0
    error_count: int = 0
    warning_count: int = 0
    content_hash: str
    quality_error_codes: list[str] = Field(default_factory=list)
    unknown_membership_session_count: int = 0
    instrument_identity_issues: int = 0
    membership_coverage_ratio: float | None = None
    capability_source_bar_ok: bool = False
    provenance_complete: bool = False
    license_status: str = "unknown"
    capability_attestation_hash: str | None = None
    package_content_hash: str | None = None
    ca_coverage_breakdown: dict[str, Any] = Field(default_factory=dict)
    # DEVELOPMENT_DATA is engineering-only; never research/paper/live eligible.
    data_class: str = ""
    extras: dict[str, Any] = Field(default_factory=dict)

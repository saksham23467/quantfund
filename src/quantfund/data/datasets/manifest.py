"""Dataset manifests, eligibility gates, and lineage metadata."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantfund.data.calendar.metadata import CALENDAR_UNVERIFIED_WARNING
from quantfund.data.grades import SourceGrade
from quantfund.data.universe.models import SURVIVORSHIP_WARNING, UniverseCompleteness


class DatasetKind(str, Enum):
    """High-level dataset class."""

    DEVELOPMENT = "development"
    RESEARCH = "research"


class ResearchEligibility(str, Enum):
    DEVELOPMENT_ONLY = "development_only"
    EXPLORATORY = "exploratory"
    RESEARCH_ELIGIBLE = "research_eligible"
    RESEARCH_READY = "research_ready"  # legacy Phase 2 alias of research_eligible
    PRODUCTION_CANDIDATE = "production_candidate"


DEVELOPMENT_WARNING = (
    "DEVELOPMENT DATASET — sourced from non-exchange-grade data and/or "
    "incomplete universe membership. NOT suitable for final strategy validation."
)


class DatasetManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    dataset_version: str
    schema_version: str = "1.0.0"
    dataset_kind: DatasetKind
    research_eligibility: ResearchEligibility
    source: str
    source_grade: SourceGrade
    dataset_status: str  # e.g. development | research
    download_id: str
    download_timestamp: datetime
    date_range_start: str
    date_range_end: str
    frequency: str = "1d"
    universe_id: str
    universe_version: str
    universe_completeness: UniverseCompleteness
    calendar_id: str
    calendar_version: str
    calendar_verified: bool = False
    calendar_content_hash: str | None = None
    calendar_source: str | None = None
    adjustment_policy: dict[str, Any]
    content_hash: str
    bar_count: int
    instrument_count: int
    raw_checksum: str | None = None
    quality_report_path: str | None = None
    lineage: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def enforce_research_gates(self) -> DatasetManifest:
        warns = list(self.warnings)
        eligibility = self.research_eligibility
        kind = self.dataset_kind
        status = self.dataset_status

        force_dev = False

        # Unverified / proxy calendar ⇒ development_only (even if other checks pass)
        if not self.calendar_verified:
            force_dev = True
            if CALENDAR_UNVERIFIED_WARNING not in warns:
                warns.insert(0, CALENDAR_UNVERIFIED_WARNING)

        # yfinance / non_exchange / Stage A ⇒ development_only
        if (
            self.source_grade == SourceGrade.NON_EXCHANGE
            or self.universe_completeness == UniverseCompleteness.CURRENT_SNAPSHOT_ONLY
            or self.source_grade == SourceGrade.SYNTHETIC
        ):
            force_dev = True
            if DEVELOPMENT_WARNING not in warns:
                warns.insert(0, DEVELOPMENT_WARNING)
            if SURVIVORSHIP_WARNING not in warns and (
                self.universe_completeness == UniverseCompleteness.CURRENT_SNAPSHOT_ONLY
            ):
                warns.insert(1, SURVIVORSHIP_WARNING)

        if force_dev:
            eligibility = ResearchEligibility.DEVELOPMENT_ONLY
            kind = DatasetKind.DEVELOPMENT
            status = "development"

        object.__setattr__(self, "research_eligibility", eligibility)
        object.__setattr__(self, "dataset_kind", kind)
        object.__setattr__(self, "dataset_status", status)
        object.__setattr__(self, "warnings", warns)
        return self

    def is_final_validation_allowed(self) -> bool:
        return self.research_eligibility in {
            ResearchEligibility.RESEARCH_ELIGIBLE,
            ResearchEligibility.RESEARCH_READY,
            ResearchEligibility.PRODUCTION_CANDIDATE,
        }

    def prominent_warnings(self) -> list[str]:
        return list(self.warnings)

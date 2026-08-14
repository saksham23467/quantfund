"""Development dataset manifest — never trusted for eligibility promotion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantfund.data.development.config import (
    DATA_CLASS_DEVELOPMENT,
    EXCHANGE_AUTHORITY,
    PROVIDER_ID,
    RESEARCH_GRADE,
    SOURCE_GRADE,
)


class DevelopmentManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    dataset_version: str
    data_class: str = DATA_CLASS_DEVELOPMENT
    source: str = PROVIDER_ID
    source_grade: str = SOURCE_GRADE
    synthetic: bool = False
    research_grade: bool = RESEARCH_GRADE
    exchange_authority: bool = EXCHANGE_AUTHORITY
    license_status: str = "unknown_or_public_source"
    research_eligible: bool = False
    paper_eligible: bool = False
    live_eligible: bool = False
    generated_at: str
    content_hash: str
    universe_mode: str = "CURRENT_SNAPSHOT"
    pit_membership: str = "unavailable"
    corporate_action_coverage: str = "none"
    delisted_coverage: str = "none"
    instrument_count: int = 0
    bar_count: int = 0
    date_coverage_start: str | None = None
    date_coverage_end: str | None = None
    quality_pass: bool = False
    quality_error_count: int = 0
    quality_warning_count: int = 0
    provider_id: str = PROVIDER_ID
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data_class")
    @classmethod
    def must_be_development(cls, v: str) -> str:
        if v != DATA_CLASS_DEVELOPMENT:
            raise ValueError(f"data_class must be {DATA_CLASS_DEVELOPMENT}")
        return v

    @field_validator("research_eligible", "paper_eligible", "live_eligible")
    @classmethod
    def never_eligible(cls, v: bool) -> bool:
        return False

    @field_validator("research_grade", "exchange_authority")
    @classmethod
    def never_authority(cls, v: bool) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def write(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )
        return path


def build_manifest(
    *,
    dataset_id: str,
    dataset_version: str,
    content_hash: str,
    synthetic: bool,
    source: str,
    universe_mode: str,
    corporate_action_coverage: str,
    delisted_coverage: str,
    instrument_count: int,
    bar_count: int,
    date_coverage_start: str | None,
    date_coverage_end: str | None,
    quality_pass: bool,
    quality_error_count: int,
    quality_warning_count: int,
    extras: dict[str, Any] | None = None,
) -> DevelopmentManifest:
    return DevelopmentManifest(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        data_class=DATA_CLASS_DEVELOPMENT,
        source=source,
        source_grade=SOURCE_GRADE,
        synthetic=synthetic,
        research_grade=False,
        exchange_authority=False,
        license_status="unknown_or_public_source",
        research_eligible=False,
        paper_eligible=False,
        live_eligible=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
        content_hash=content_hash,
        universe_mode=universe_mode,
        pit_membership="unavailable"
        if universe_mode == "CURRENT_SNAPSHOT"
        else "partial",
        corporate_action_coverage=corporate_action_coverage,
        delisted_coverage=delisted_coverage,
        instrument_count=instrument_count,
        bar_count=bar_count,
        date_coverage_start=date_coverage_start,
        date_coverage_end=date_coverage_end,
        quality_pass=quality_pass,
        quality_error_count=quality_error_count,
        quality_warning_count=quality_warning_count,
        provider_id=PROVIDER_ID,
        extras=dict(extras or {}),
    )

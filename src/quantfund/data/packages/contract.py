"""Formal versioned research package contract (Phase 7).

Authority is never inferred from filenames — only from declared, validated fields.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "quantfund_research_package_v1"


class ResearchPackageManifest(BaseModel):
    """Canonical package.json schema for external research packages."""

    model_config = ConfigDict(frozen=True, extra="allow")

    package_id: str
    package_version: str
    provider: str
    source_grade: str
    schema_version: str = SCHEMA_VERSION
    exchange_authority: bool = False
    license_status: str = "unknown"
    acquisition_timestamp: str | None = None
    coverage_start: str | None = None
    coverage_end: str | None = None
    frequencies: list[str] = Field(default_factory=lambda: ["1d"])
    exchanges: list[str] = Field(default_factory=list)
    asset_classes: list[str] = Field(default_factory=lambda: ["equity"])
    checksum_algorithm: str = "sha256"
    synthetic: bool = False
    provider_name: str | None = None
    vendor: str | None = None  # alias / display vendor name
    source: str | None = None
    licensing_notes: str = ""
    usage_notes: str = ""
    limitations: list[str] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None
    generation_timestamp: str | None = None
    test_fixture_only: bool = False

    def is_research_eligible_capable_declared(self) -> bool:
        """Package *declaration* only — not actual eligibility."""
        if self.synthetic or self.source_grade in {"synthetic", "non_exchange"}:
            return False
        return self.source_grade in {"exchange", "paid"} and self.license_status not in {
            "unknown",
            "prohibited",
            "expired",
        }

    @field_validator("source_grade")
    @classmethod
    def grade_known(cls, v: str) -> str:
        allowed = {"exchange", "paid", "non_exchange", "synthetic"}
        if v not in allowed:
            raise ValueError(f"unsupported source_grade={v}; allowed={sorted(allowed)}")
        return v

    @field_validator("schema_version")
    @classmethod
    def schema_ok(cls, v: str) -> str:
        if not v.startswith("quantfund_research_package_"):
            raise ValueError(f"unsupported schema_version={v}")
        return v

    def is_synthetic(self) -> bool:
        return self.synthetic or self.source_grade == "synthetic"

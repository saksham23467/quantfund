"""Provenance metadata for every download / dataset transformation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProvenanceRecord(BaseModel):
    """Immutable provenance attached to RAW downloads and research datasets."""

    model_config = ConfigDict(frozen=True)

    source: str
    provider: str
    download_timestamp: datetime
    request_parameters: dict[str, Any] = Field(default_factory=dict)
    source_identifiers: dict[str, str] = Field(default_factory=dict)
    content_hashes: dict[str, str] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    license_ref: str | None = None
    package_id: str | None = None
    package_version: str | None = None
    # Phase 7 explicit legal / acquisition fields
    legal_source: str | None = None
    license_status: str | None = None
    redistribution_allowed: bool | None = None
    research_use_allowed: bool | None = None
    exchange_authority: bool | None = None
    acquisition_method: str | None = None
    acquisition_timestamp: datetime | None = None
    package_hash: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    def to_manifest_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def is_complete_for_research(self) -> bool:
        """Minimal provenance completeness for research certification."""
        return bool(
            self.provider
            and self.download_timestamp
            and (self.package_hash or self.content_hashes)
            and self.license_status
            and self.license_status != "unknown"
        )

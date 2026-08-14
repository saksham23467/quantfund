"""Universe definition and versioned membership models.

Stage A uses completeness=current_snapshot_only and does NOT solve survivorship.
Stage B uses interval membership records (member_from / member_to).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


SURVIVORSHIP_WARNING = (
    "NOT POINT-IN-TIME. UNSUITABLE FOR FINAL STRATEGY EVALUATION."
)
TODAY_CONSTITUENTS_WARNING = (
    "Historical period uses current-snapshot constituents — rejected for research."
)


class UniverseCompleteness(str, Enum):
    CURRENT_SNAPSHOT_ONLY = "current_snapshot_only"
    PARTIAL_PIT = "partial_pit"
    FULL_PIT = "full_pit"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    VERIFIED = "verified"


class UniverseDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    universe_id: str
    name: str
    description: str = ""
    methodology_notes: str = ""


class UniverseMember(BaseModel):
    """Legacy snapshot member (Stage A). Prefer UniverseMembership for PIT."""

    model_config = ConfigDict(frozen=True)

    instrument_id: str
    symbol: str
    provider_symbol: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UniverseMembership(BaseModel):
    """Point-in-time membership interval for an instrument."""

    model_config = ConfigDict(frozen=True)

    universe_id: str
    instrument_id: str
    symbol: str
    member_from: date
    member_to: date | None = None  # None = open-ended (still member)
    source: str
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered(self) -> UniverseMembership:
        if self.member_to is not None and self.member_to < self.member_from:
            raise ValueError("member_to must be >= member_from")
        return self

    def covers(self, on: date) -> bool:
        if on < self.member_from:
            return False
        if self.member_to is not None and on > self.member_to:
            return False
        return True


class UniverseVersion(BaseModel):
    """A concrete membership snapshot or PIT interval set."""

    model_config = ConfigDict(frozen=True)

    universe_id: str
    universe_version: str
    completeness: UniverseCompleteness
    as_of_date: date
    effective_start: date | None = None
    effective_end: date | None = None
    source: str
    members: list[UniverseMember] = Field(default_factory=list)
    memberships: list[UniverseMembership] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    notes: str = ""

    def model_post_init(self, __context: object) -> None:
        warns = list(self.warnings)
        if self.completeness == UniverseCompleteness.CURRENT_SNAPSHOT_ONLY:
            if SURVIVORSHIP_WARNING not in warns:
                warns.insert(0, SURVIVORSHIP_WARNING)
            object.__setattr__(self, "warnings", warns)

    @property
    def symbols(self) -> list[str]:
        if self.memberships:
            return sorted({m.symbol for m in self.memberships})
        return [m.symbol for m in self.members]

    @property
    def instrument_ids(self) -> list[str]:
        if self.memberships:
            return sorted({m.instrument_id for m in self.memberships})
        return [m.instrument_id for m in self.members]

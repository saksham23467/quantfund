"""ResearchDatasetPackage schema — versioned, provenance-carrying, fail-closed.

Field names follow the requested contract. Every record embeds a
:class:`SourceProvenance` block so each value is traceable to its authoritative
source. No field is ever inferred from today's universe, and nothing is
fabricated: absent facts are ``None`` (UNKNOWN), which downstream certification
treats as fail-closed rather than a silent pass.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quantfund.data.grades import SourceGrade

RESEARCH_DATASET_SCHEMA_VERSION = "research_dataset_package_v1"


class SourceType(str, Enum):
    EXCHANGE_DIRECT = "exchange_direct"
    LICENSED_VENDOR = "licensed_vendor"
    BROKER_REDISTRIBUTED = "broker_redistributed"
    FREE_WEB = "free_web"
    SYNTHETIC = "synthetic"


class TerminalEventType(str, Enum):
    DELISTED = "delisted"
    MERGED = "merged"
    ACQUIRED = "acquired"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


class SessionType(str, Enum):
    OPEN_SESSION = "OPEN_SESSION"
    CLOSED_SESSION = "CLOSED_SESSION"
    SPECIAL_SESSION = "SPECIAL_SESSION"


class SourceProvenance(BaseModel):
    """Provenance metadata attached to every record."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    source_type: SourceType
    source_license: str
    retrieved_at: datetime
    source_ref: str | None = None
    source_url: str | None = None
    notes: str = ""


class OHLCVBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    isin: str | None
    instrument_id: str | None
    instrument_token: int | None = None
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    provenance: SourceProvenance


class IdentityRecord(BaseModel):
    """Historical security-master mapping. Ticker is never permanent identity."""

    model_config = ConfigDict(frozen=True)

    isin: str
    exchange: str
    instrument_id: str
    symbol: str
    valid_from: date
    valid_to: date | None = None  # None = still valid
    provenance: SourceProvenance


class MembershipRecord(BaseModel):
    """Point-in-time index membership interval."""

    model_config = ConfigDict(frozen=True)

    universe_id: str
    universe_version: str
    symbol: str
    isin: str
    member_from: date
    member_to: date | None = None  # None = still a member
    provenance: SourceProvenance


class DelistingRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    isin: str
    symbol: str
    delisting_date: date
    terminal_event_type: TerminalEventType
    successor_isin: str | None = None
    provenance: SourceProvenance


class CalendarSessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    exchange: str
    session_date: date
    is_open: bool
    session_type: SessionType
    provenance: SourceProvenance


class CorporateActionRecord(BaseModel):
    """Corporate action kept SEPARATE from RAW execution prices."""

    model_config = ConfigDict(frozen=True)

    isin: str
    symbol: str
    ex_date: date
    action_type: str
    ratio_num: float | None = None
    ratio_den: float | None = None
    cash_amount: float | None = None
    source: str
    provenance: SourceProvenance


class ResearchDatasetManifest(BaseModel):
    """Top-level dataset manifest. source_grade is honest, never forged."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = RESEARCH_DATASET_SCHEMA_VERSION
    dataset_id: str
    dataset_version: str
    source_name: str
    source_type: SourceType
    source_license: str
    source_grade: SourceGrade
    data_class: str
    download_timestamp: datetime
    coverage_start: date
    coverage_end: date
    exchange: str
    currency: str
    exchange_authority: bool = False
    license_status: str = "unknown"


class ResearchDatasetPackage(BaseModel):
    """A complete, provenance-carrying research dataset.

    Empty sub-collections mean the corresponding authoritative data is ABSENT
    (UNKNOWN), which certification fails closed on — never treated as complete.
    """

    model_config = ConfigDict(frozen=True)

    manifest: ResearchDatasetManifest
    ohlcv: list[OHLCVBar] = Field(default_factory=list)
    identity: list[IdentityRecord] = Field(default_factory=list)
    membership: list[MembershipRecord] = Field(default_factory=list)
    delistings: list[DelistingRecord] = Field(default_factory=list)
    calendar: list[CalendarSessionRecord] = Field(default_factory=list)
    corporate_actions: list[CorporateActionRecord] = Field(default_factory=list)

    def symbols(self) -> list[str]:
        return sorted({b.symbol for b in self.ohlcv})

    def isins(self) -> list[str]:
        return sorted({b.isin for b in self.ohlcv if b.isin})

    def canonical_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

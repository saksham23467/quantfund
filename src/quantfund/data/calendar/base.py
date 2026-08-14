"""CalendarProvider interface.

Independent from DataProvider — data vendors must never define trading-day rules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from quantfund.data.calendar.metadata import CalendarMetadata


class SessionType(str, Enum):
    REGULAR = "regular"
    HOLIDAY = "holiday"
    WEEKEND = "weekend"
    SPECIAL = "special"
    UNKNOWN = "unknown"
    OUT_OF_COVERAGE = "out_of_coverage"


class TradingSession(BaseModel):
    """One calendar day in an exchange calendar."""

    model_config = ConfigDict(frozen=True)

    session_date: date
    is_open: bool
    session_type: SessionType = SessionType.REGULAR
    note: str | None = None


class CalendarProvider(ABC):
    """Versioned, reproducible trading-session source."""

    @property
    @abstractmethod
    def calendar_id(self) -> str:
        """Logical calendar identifier recorded in dataset manifests."""

    @property
    @abstractmethod
    def calendar_version(self) -> str:
        """Reproducible version string for this calendar snapshot/implementation."""

    @property
    @abstractmethod
    def timezone(self) -> str:
        """IANA timezone name (e.g. Asia/Kolkata)."""

    @property
    @abstractmethod
    def verified(self) -> bool:
        """True only if this calendar is independently verified for its market."""

    @abstractmethod
    def metadata(self) -> CalendarMetadata:
        """Full auditable metadata including content hash and coverage window."""

    @abstractmethod
    def is_session(self, day: date | datetime | str) -> bool:
        """Return True if ``day`` is an open trading session."""

    @abstractmethod
    def sessions_in_range(self, start: date, end: date) -> list[date]:
        """Inclusive list of open session dates in [start, end]."""

    @abstractmethod
    def describe_day(self, day: date) -> TradingSession:
        """Classify a calendar day (open / weekend / holiday / special)."""

    def expected_sessions(self, start: date, end: date) -> set[date]:
        """Set form of ``sessions_in_range`` for validation."""
        return set(self.sessions_in_range(start, end))

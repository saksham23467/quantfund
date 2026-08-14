"""Calendar metadata required for dataset lineage and verification gates."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


CALENDAR_UNVERIFIED_WARNING = (
    "Calendar is not verified for NSE equity sessions."
)


class CalendarMetadata(BaseModel):
    """Auditable calendar identity recorded on datasets and quality reports."""

    model_config = ConfigDict(frozen=True)

    calendar_id: str
    calendar_version: str
    source: str
    source_retrieved_at: datetime | None = None
    effective_start: date | None = None
    effective_end: date | None = None
    timezone: str = "Asia/Kolkata"
    content_hash: str
    verified: bool = False
    notes: list[str] = Field(default_factory=list)

    def to_manifest_dict(self) -> dict:
        return self.model_dump(mode="json")

"""Structured data quality reports with ERROR / WARNING / INFO."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class QualityIssue(BaseModel):
    severity: Severity
    code: str
    message: str
    symbol: str | None = None
    timestamp: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class QualityReport(BaseModel):
    dataset_id: str | None = None
    source: str | None = None
    universe_id: str | None = None
    universe_version: str | None = None
    calendar_id: str | None = None
    calendar_version: str | None = None
    calendar_verified: bool | None = None
    instrument_count: int = 0
    date_range_start: str | None = None
    date_range_end: str | None = None
    row_count: int = 0
    missing_sessions: int = 0  # unique open sessions with >=1 missing bar
    missing_bars: int = 0  # symbol-session missing pairs
    expected_absences: int = 0
    duplicate_bars: int = 0
    invalid_ohlc: int = 0
    negative_or_zero_volume: int = 0
    stale_prices: int = 0
    timestamp_problems: int = 0
    corporate_action_inconsistencies: int = 0
    instrument_identity_problems: int = 0
    unknown_membership_periods: int = 0
    invalid_rows: int = 0
    corporate_action_count: int = 0
    adjustment_policy: dict[str, Any] | None = None
    issues: list[QualityIssue] = Field(default_factory=list)
    warnings_text: list[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    def add(self, issue: QualityIssue) -> None:
        self.issues.append(issue)
        if issue.severity == Severity.WARNING:
            self.warnings_text.append(issue.message)

    def raise_if_errors(self) -> None:
        if self.error_count:
            codes = sorted({i.code for i in self.issues if i.severity == Severity.ERROR})
            raise ValueError(
                f"QualityReport has {self.error_count} ERROR(s): {', '.join(codes)}"
            )

    def error_codes(self) -> list[str]:
        return sorted({i.code for i in self.issues if i.severity == Severity.ERROR})

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        data["error_count"] = self.error_count
        data["warning_count"] = self.warning_count
        data["error_codes"] = self.error_codes()
        return data

"""Quality gating for Phase 17A — report, do not repair."""

from __future__ import annotations

from datetime import date
from typing import Any

from quantfund.data.calendar.nse import DEFAULT_NSE_CALENDAR_VERSION, NSECalendarProvider
from quantfund.data.models import MarketBar
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.quality.report import Severity
from quantfund.data.zerodha_hist.real_validation import calendar_coverage


# Structural issues that must DATA_BLOCK
BLOCKING_CODES = frozenset(
    {
        "duplicate_timestamp",
        "invalid_ohlc",
        "missing_ohlc",
        "non_positive_price",
        "negative_volume",
        "unordered_timestamps",
    }
)


def run_symbol_quality(
    bars: list[MarketBar],
    *,
    dataset_id: str,
    calendar_version: str | None = None,
    coverage_start: date | None = None,
    coverage_end: date | None = None,
) -> dict[str, Any]:
    cal_version = calendar_version or DEFAULT_NSE_CALENDAR_VERSION
    cal = NSECalendarProvider(calendar_version=cal_version)
    report = run_quality_checks(
        bars,
        calendar=cal,
        instruments=[],
        provider_capabilities=None,
        dataset_id=dataset_id,
        source="zerodha_historical_api",
    )
    errors = [i for i in report.issues if i.severity is Severity.ERROR]
    warnings = [i for i in report.issues if i.severity is Severity.WARNING]
    blocking = [i for i in errors if i.code in BLOCKING_CODES]
    start = coverage_start or (min(b.timestamp for b in bars).date() if bars else None)
    end = coverage_end or (max(b.timestamp for b in bars).date() if bars else None)
    cov = (
        calendar_coverage(bars, start=start, end=end, calendar_version=cal_version)
        if start and end
        else {"coverage_ratio": 0.0}
    )
    return {
        "errors": len(errors),
        "warnings": len(warnings),
        "blocking_errors": len(blocking),
        "data_blocked": len(blocking) > 0 or not bars,
        "issue_codes": sorted({i.code for i in errors}),
        "issues": [
            {"severity": i.severity.value, "code": i.code, "message": i.message}
            for i in report.issues[:40]
        ],
        "calendar": cov,
        "limitation": (
            "non_blocking_calendar_or_expected_absence_issues"
            if errors and not blocking
            else None
        ),
    }

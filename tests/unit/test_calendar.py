"""CalendarProvider tests: weekends/holidays/NSE verification."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from quantfund.data.calendar.exchange_calendars_provider import ExchangeCalendarsProvider
from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.models import MarketBar
from quantfund.data.quality.checks import run_quality_checks


def test_saturday_sunday_not_open_on_nse():
    cal = NSECalendarProvider()
    assert cal.is_session(date(2024, 1, 6)) is False
    assert cal.is_session(date(2024, 1, 7)) is False
    assert cal.describe_day(date(2024, 1, 6)).session_type.value == "weekend"


def test_republic_day_holiday_closed_on_nse():
    cal = NSECalendarProvider()
    assert cal.is_session(date(2024, 1, 26)) is False
    assert cal.describe_day(date(2024, 1, 26)).session_type.value == "holiday"


def test_weekend_not_reported_as_missing_error():
    open_days = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)]
    cal = FakeCalendarProvider(open_days)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, d),
            symbol="TEST",
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        )
        for d in (2, 3, 4, 5)
    ]
    report = run_quality_checks(
        bars, calendar=cal, start=date(2024, 1, 2), end=date(2024, 1, 6)
    )
    missing_errors = [i for i in report.issues if i.code == "missing_open_session"]
    expected_info = [i for i in report.issues if i.code == "expected_absence"]
    assert missing_errors == []
    assert any(i.timestamp == "2024-01-06" for i in expected_info)


def test_missing_open_session_is_error():
    open_days = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    cal = FakeCalendarProvider(open_days)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 4),
            symbol="TEST",
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        ),
    ]
    report = run_quality_checks(
        bars, calendar=cal, start=date(2024, 1, 2), end=date(2024, 1, 4)
    )
    assert any(
        i.code == "missing_open_session" and i.timestamp == "2024-01-03" for i in report.issues
    )
    assert report.error_count >= 1


def test_nse_calendar_is_versioned_and_verified():
    cal = NSECalendarProvider()
    meta = cal.metadata()
    assert meta.calendar_id == "NSE_EQ"
    assert meta.calendar_version == "nse_eq_v2018_2026_r1"
    assert meta.verified is True
    assert meta.content_hash.startswith("sha256:")
    assert meta.timezone == "Asia/Kolkata"
    assert meta.effective_start == date(2018, 1, 1)
    assert meta.effective_end == date(2026, 12, 31)
    assert meta.source_retrieved_at is not None


def test_prior_calendar_version_remains_loadable_and_immutable():
    """Older versions are not overwritten when coverage expands."""
    old = NSECalendarProvider(calendar_version="nse_eq_v2024_2025_r1")
    assert old.calendar_version == "nse_eq_v2024_2025_r1"
    assert old.metadata().effective_start == date(2024, 1, 1)
    assert old.is_session(date(2023, 1, 3)) is False  # out of that version's coverage
    mid = NSECalendarProvider(calendar_version="nse_eq_v2023_2025_r1")
    assert mid.is_session(date(2023, 1, 3)) is True  # Tuesday, not a 2023 holiday
    assert mid.is_session(date(2023, 11, 12)) is True  # Muhurat Sunday
    new = NSECalendarProvider(calendar_version="nse_eq_v2018_2026_r1")
    assert new.is_session(date(2018, 1, 1)) is True  # Monday
    assert new.is_session(date(2017, 12, 29)) is False  # outside coverage


def test_xbom_proxy_is_explicitly_unverified():
    cal = ExchangeCalendarsProvider()
    assert cal.verified is False
    assert "PROXY" in cal.calendar_id or "XBOM" in cal.calendar_id
    assert "NSE_EQ" != cal.calendar_id
    with pytest.raises(ValueError, match="NSE"):
        ExchangeCalendarsProvider(calendar_id="NSE_EQ")

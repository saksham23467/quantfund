"""Verified NSE calendar fixture tests with documented sources."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.models import MarketBar
from quantfund.data.quality.checks import run_quality_checks
from datetime import datetime

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "phase15" / "nse_calendar_verification.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_verification_fixture_open_closed_weekend_special():
    data = _fixture()
    cal = NSECalendarProvider()
    assert cal.calendar_version == data["calendar_version"]
    assert cal.verified is True

    for item in data["open_sessions"]:
        d = date.fromisoformat(item["date"])
        assert cal.is_session(d) is True, item
        desc = cal.describe_day(d)
        assert desc.is_open is True
        if "Muhurat" in item["reason"]:
            assert desc.session_type.value == "special"

    for item in data["closed_holidays"]:
        d = date.fromisoformat(item["date"])
        assert cal.is_session(d) is False, item
        assert cal.describe_day(d).session_type.value == "holiday"

    for item in data["weekends"]:
        d = date.fromisoformat(item["date"])
        assert cal.is_session(d) is False, item
        # Sunday Republic Day 2025 is weekend (also a holiday on weekend)
        assert cal.describe_day(d).session_type.value in {"weekend", "holiday"}


def test_wrong_calendar_hides_missing_bar_as_expected_absence():
    """False confidence: wrong calendar treats a true trading day as absence.

    If a bar is missing on 2024-01-25 (NSE open day) but the calendar wrongly
    marks it closed, quality checks report expected_absence instead of ERROR.
    """
    # Bars missing 2024-01-25
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 24),
            symbol="TEST",
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 29),
            symbol="TEST",
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        ),
    ]

    nse = NSECalendarProvider()
    correct = run_quality_checks(
        bars, calendar=nse, start=date(2024, 1, 24), end=date(2024, 1, 29)
    )
    assert any(
        i.code == "missing_open_session" and i.timestamp == "2024-01-25"
        for i in correct.issues
    ), "Verified NSE calendar must fail loudly on missing 2024-01-25 bar"

    # Wrong calendar: pretends 2024-01-25 is not an open session
    wrong = FakeCalendarProvider(
        [date(2024, 1, 24), date(2024, 1, 29)],
        calendar_id="WRONG_CAL",
        verified=False,
    )
    wrong_report = run_quality_checks(
        bars, calendar=wrong, start=date(2024, 1, 24), end=date(2024, 1, 29)
    )
    assert not any(
        i.code == "missing_open_session" and i.timestamp == "2024-01-25"
        for i in wrong_report.issues
    )
    assert any(
        i.code == "expected_absence" and i.timestamp == "2024-01-25"
        for i in wrong_report.issues
    )


def test_unverified_calendar_warning_in_quality_report():
    cal = FakeCalendarProvider([date(2024, 1, 2)], verified=False)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
    ]
    report = run_quality_checks(bars, calendar=cal)
    assert report.calendar_verified is False
    assert report.calendar_id == "FAKE_TEST"
    assert any(i.code == "calendar_unverified" for i in report.issues)

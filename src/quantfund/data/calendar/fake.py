"""Deterministic calendar for tests (explicit open sessions only)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from quantfund.data.calendar.base import CalendarProvider, SessionType, TradingSession
from quantfund.data.calendar.metadata import CalendarMetadata
from quantfund.data.ingest.checksums import hash_json


class FakeCalendarProvider(CalendarProvider):
    """Test calendar: only explicitly provided dates are open sessions."""

    def __init__(
        self,
        open_sessions: list[date],
        *,
        calendar_id: str = "FAKE_TEST",
        calendar_version: str = "fake_v1",
        timezone: str = "Asia/Kolkata",
        verified: bool = False,
        closed_as_expected_absence: bool = True,
    ) -> None:
        self._open = set(open_sessions)
        self._calendar_id = calendar_id
        self._calendar_version = calendar_version
        self._timezone = timezone
        self._verified = verified
        self._closed_as_expected_absence = closed_as_expected_absence

    @property
    def calendar_id(self) -> str:
        return self._calendar_id

    @property
    def calendar_version(self) -> str:
        return self._calendar_version

    @property
    def timezone(self) -> str:
        return self._timezone

    @property
    def verified(self) -> bool:
        return self._verified

    def metadata(self) -> CalendarMetadata:
        return CalendarMetadata(
            calendar_id=self.calendar_id,
            calendar_version=self.calendar_version,
            source="synthetic_test_fixture",
            source_retrieved_at=datetime.now(timezone.utc),
            effective_start=min(self._open) if self._open else None,
            effective_end=max(self._open) if self._open else None,
            timezone=self.timezone,
            content_hash=hash_json(
                {
                    "open_sessions": sorted(d.isoformat() for d in self._open),
                    "verified": self._verified,
                }
            ),
            verified=self._verified,
            notes=["Synthetic test calendar — not for production research."],
        )

    def is_session(self, day: date | datetime | str) -> bool:
        if isinstance(day, datetime):
            d = day.date()
        elif isinstance(day, date):
            d = day
        else:
            d = date.fromisoformat(str(day)[:10])
        return d in self._open

    def sessions_in_range(self, start: date, end: date) -> list[date]:
        out: list[date] = []
        cur = start
        while cur <= end:
            if cur in self._open:
                out.append(cur)
            cur += timedelta(days=1)
        return out

    def describe_day(self, day: date) -> TradingSession:
        if self.is_session(day):
            return TradingSession(
                session_date=day, is_open=True, session_type=SessionType.REGULAR
            )
        if day.weekday() >= 5:
            return TradingSession(
                session_date=day,
                is_open=False,
                session_type=SessionType.WEEKEND,
                note="weekend",
            )
        return TradingSession(
            session_date=day,
            is_open=False,
            session_type=SessionType.HOLIDAY,
            note="holiday",
        )

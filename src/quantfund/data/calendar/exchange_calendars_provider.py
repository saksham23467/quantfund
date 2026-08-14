"""UNVERIFIED BSE/XBOM proxy calendar via exchange-calendars.

CRITICAL
--------
This is NOT an NSE calendar. exchange-calendars does not ship XNSE.
Using this provider MUST keep research_eligibility = development_only.
Prefer NSECalendarProvider for NSE equity session correctness.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from functools import lru_cache

import exchange_calendars as xcals
import pandas as pd

from quantfund.data.calendar.base import CalendarProvider, SessionType, TradingSession
from quantfund.data.calendar.metadata import CalendarMetadata
from quantfund.data.ingest.checksums import hash_json

DEFAULT_LOGICAL_CALENDAR_ID = "XBOM_PROXY_UNVERIFIED"
DEFAULT_BACKEND_CALENDAR = "XBOM"
PROVIDER_IMPL_VERSION = "exchange_calendars_xbom_proxy_v2"


def _to_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@lru_cache(maxsize=4)
def _load_calendar(backend_name: str):
    return xcals.get_calendar(backend_name)


class ExchangeCalendarsProvider(CalendarProvider):
    """BSE (XBOM) sessions via exchange-calendars — unverified NSE proxy."""

    def __init__(
        self,
        *,
        calendar_id: str = DEFAULT_LOGICAL_CALENDAR_ID,
        backend_name: str = DEFAULT_BACKEND_CALENDAR,
        calendar_version: str | None = None,
    ) -> None:
        if "NSE" in calendar_id.upper() and "PROXY" not in calendar_id.upper():
            raise ValueError(
                "Refusing to label XBOM-backed calendar as NSE without PROXY marker. "
                "Use NSECalendarProvider for verified NSE sessions."
            )
        self._calendar_id = calendar_id
        self._backend_name = backend_name
        self._calendar = _load_calendar(backend_name)
        pkg_ver = getattr(xcals, "__version__", "unknown")
        self._calendar_version = (
            calendar_version or f"{PROVIDER_IMPL_VERSION}+pkg_{pkg_ver}"
        )

    @property
    def calendar_id(self) -> str:
        return self._calendar_id

    @property
    def calendar_version(self) -> str:
        return self._calendar_version

    @property
    def timezone(self) -> str:
        tz = self._calendar.tz
        return str(getattr(tz, "zone", None) or getattr(tz, "key", None) or tz)

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def verified(self) -> bool:
        return False

    def metadata(self) -> CalendarMetadata:
        return CalendarMetadata(
            calendar_id=self.calendar_id,
            calendar_version=self.calendar_version,
            source=f"exchange_calendars:{self._backend_name} (UNVERIFIED NSE proxy)",
            source_retrieved_at=datetime.now(timezone.utc),
            effective_start=None,
            effective_end=None,
            timezone=self.timezone,
            content_hash=hash_json(
                {
                    "backend": self._backend_name,
                    "calendar_version": self.calendar_version,
                    "verified": False,
                }
            ),
            verified=False,
            notes=[
                "NOT verified for NSE equity sessions.",
                "Do not treat as NSE_EQ.",
            ],
        )

    def is_session(self, day: date | datetime | str) -> bool:
        d = _to_date(day)
        return bool(self._calendar.is_session(pd.Timestamp(d)))

    def sessions_in_range(self, start: date, end: date) -> list[date]:
        if end < start:
            return []
        sessions = self._calendar.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
        return [ts.date() for ts in sessions]

    def describe_day(self, day: date) -> TradingSession:
        d = _to_date(day)
        if self.is_session(d):
            return TradingSession(
                session_date=d,
                is_open=True,
                session_type=SessionType.REGULAR,
                note="XBOM_PROXY_UNVERIFIED",
            )
        if d.weekday() >= 5:
            return TradingSession(
                session_date=d,
                is_open=False,
                session_type=SessionType.WEEKEND,
                note="weekend",
            )
        return TradingSession(
            session_date=d,
            is_open=False,
            session_type=SessionType.HOLIDAY,
            note=f"non_session via unverified {self._backend_name} proxy",
        )

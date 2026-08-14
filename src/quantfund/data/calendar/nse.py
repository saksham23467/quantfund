"""Curated, version-controlled NSE equity CalendarProvider.

Approach: auditable holiday/special-session dataset under data/calendars/,
sourced from NSE Capital Market holiday circulars — not BSE/XBOM proxy.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from quantfund.config import PATHS
from quantfund.data.calendar.base import CalendarProvider, SessionType, TradingSession
from quantfund.data.calendar.metadata import CalendarMetadata
from quantfund.data.ingest.checksums import hash_json

# Latest verified default. Older versions remain on disk and loadable by path/version.
DEFAULT_NSE_CALENDAR_VERSION = "nse_eq_v2018_2026_r1"


def _to_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def nse_calendar_dir(calendar_version: str = DEFAULT_NSE_CALENDAR_VERSION) -> Path:
    return PATHS.calendars_dir / "nse_eq" / f"calendar_version={calendar_version}"


def default_nse_calendar_dir() -> Path:
    return nse_calendar_dir(DEFAULT_NSE_CALENDAR_VERSION)


@lru_cache(maxsize=8)
def _load_calendar_payload(path_str: str) -> dict:
    path = Path(path_str)
    return json.loads(path.read_text(encoding="utf-8"))


class NSECalendarProvider(CalendarProvider):
    """NSE equity sessions from a curated, versioned calendar file."""

    def __init__(
        self,
        calendar_dir: Path | None = None,
        *,
        calendar_version: str | None = None,
    ) -> None:
        if calendar_dir is not None and calendar_version is not None:
            raise ValueError("Pass calendar_dir or calendar_version, not both")
        if calendar_dir is not None:
            self._dir = Path(calendar_dir)
        elif calendar_version is not None:
            self._dir = nse_calendar_dir(calendar_version)
        else:
            self._dir = default_nse_calendar_dir()
        payload_path = self._dir / "calendar.json"
        if not payload_path.exists():
            raise FileNotFoundError(f"NSE calendar file missing: {payload_path}")
        self._payload = _load_calendar_payload(str(payload_path.resolve()))
        self._content_hash = hash_json(self._payload)

        self._holidays = {
            date.fromisoformat(item["date"]): item.get("name", "holiday")
            for item in self._payload.get("full_holidays", [])
        }
        self._special: dict[date, dict] = {
            date.fromisoformat(item["date"]): item
            for item in self._payload.get("special_sessions", [])
        }
        self._effective_start = date.fromisoformat(self._payload["effective_start"])
        self._effective_end = date.fromisoformat(self._payload["effective_end"])

    @property
    def calendar_id(self) -> str:
        return str(self._payload["calendar_id"])

    @property
    def calendar_version(self) -> str:
        return str(self._payload["calendar_version"])

    @property
    def timezone(self) -> str:
        return str(self._payload.get("timezone", "Asia/Kolkata"))

    @property
    def verified(self) -> bool:
        return bool(self._payload.get("verified", False))

    @property
    def content_hash(self) -> str:
        return self._content_hash

    def metadata(self) -> CalendarMetadata:
        retrieved = self._payload.get("source_retrieved_at")
        return CalendarMetadata(
            calendar_id=self.calendar_id,
            calendar_version=self.calendar_version,
            source=str(self._payload.get("source", "unknown")),
            source_retrieved_at=datetime.fromisoformat(retrieved) if retrieved else None,
            effective_start=self._effective_start,
            effective_end=self._effective_end,
            timezone=self.timezone,
            content_hash=self._content_hash,
            verified=self.verified,
            notes=list(self._payload.get("notes", [])),
        )

    def in_coverage(self, day: date) -> bool:
        return self._effective_start <= day <= self._effective_end

    def is_session(self, day: date | datetime | str) -> bool:
        d = _to_date(day)
        if not self.in_coverage(d):
            return False
        if d in self._special:
            return bool(self._special[d].get("is_open", True))
        if d.weekday() >= 5:
            return False
        if d in self._holidays:
            return False
        return True

    def sessions_in_range(self, start: date, end: date) -> list[date]:
        if end < start:
            return []
        out: list[date] = []
        cur = start
        while cur <= end:
            if self.is_session(cur):
                out.append(cur)
            cur += timedelta(days=1)
        return out

    def describe_day(self, day: date) -> TradingSession:
        d = _to_date(day)
        if not self.in_coverage(d):
            return TradingSession(
                session_date=d,
                is_open=False,
                session_type=SessionType.OUT_OF_COVERAGE,
                note=(
                    f"outside verified coverage "
                    f"[{self._effective_start} .. {self._effective_end}]"
                ),
            )
        if d in self._special:
            spec = self._special[d]
            return TradingSession(
                session_date=d,
                is_open=bool(spec.get("is_open", True)),
                session_type=SessionType.SPECIAL,
                note=spec.get("note") or spec.get("name"),
            )
        if d.weekday() >= 5:
            return TradingSession(
                session_date=d,
                is_open=False,
                session_type=SessionType.WEEKEND,
                note="weekend",
            )
        if d in self._holidays:
            return TradingSession(
                session_date=d,
                is_open=False,
                session_type=SessionType.HOLIDAY,
                note=self._holidays[d],
            )
        return TradingSession(
            session_date=d,
            is_open=True,
            session_type=SessionType.REGULAR,
            note=None,
        )

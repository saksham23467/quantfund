"""Market session state for real-time paper — uses existing calendar."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from quantfund.data.calendar.base import CalendarProvider

IST = ZoneInfo("Asia/Kolkata")

# NSE equity cash market hours (regular). Special sessions come from calendar.
NSE_PRE_OPEN = time(9, 0)
NSE_OPEN = time(9, 15)
NSE_CLOSING_START = time(15, 20)
NSE_CLOSE = time(15, 30)


class MarketSessionState(str, Enum):
    PRE_MARKET = "PRE_MARKET"
    OPEN = "OPEN"
    TRADING = "TRADING"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    HALTED = "HALTED"


def resolve_session_state(
    when: datetime,
    calendar: CalendarProvider,
    *,
    halted: bool = False,
    daily_bar_mode: bool = False,
) -> MarketSessionState:
    """Resolve session state from calendar + NSE hours.

    ``daily_bar_mode``: daily bars are often stamped at close; if the calendar
    says the day is a session, treat as TRADING (do not invent special sessions).
    """
    if halted:
        return MarketSessionState.HALTED
    local = when.astimezone(IST) if when.tzinfo else when.replace(tzinfo=IST)
    d: date = local.date()
    if not calendar.is_session(d):
        return MarketSessionState.CLOSED
    if daily_bar_mode:
        return MarketSessionState.TRADING
    t = local.time()
    if t < NSE_PRE_OPEN:
        return MarketSessionState.CLOSED
    if NSE_PRE_OPEN <= t < NSE_OPEN:
        return MarketSessionState.PRE_MARKET
    if NSE_OPEN <= t < NSE_CLOSING_START:
        if t < time(9, 16):
            return MarketSessionState.OPEN
        return MarketSessionState.TRADING
    if NSE_CLOSING_START <= t <= NSE_CLOSE:
        return MarketSessionState.CLOSING
    return MarketSessionState.CLOSED


def orders_allowed(state: MarketSessionState) -> bool:
    return state in {
        MarketSessionState.OPEN,
        MarketSessionState.TRADING,
        MarketSessionState.CLOSING,
    }


def session_info(
    when: datetime,
    calendar: CalendarProvider,
    *,
    halted: bool = False,
    daily_bar_mode: bool = False,
) -> dict[str, Any]:
    state = resolve_session_state(
        when, calendar, halted=halted, daily_bar_mode=daily_bar_mode
    )
    return {
        "state": state.value,
        "orders_allowed": orders_allowed(state),
        "local_time": when.astimezone(IST).isoformat() if when.tzinfo else str(when),
        "calendar_session": calendar.is_session(
            when.astimezone(IST).date() if when.tzinfo else when.date()
        ),
        "daily_bar_mode": daily_bar_mode,
    }

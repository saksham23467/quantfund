"""Controlled paper session durations — no auto-graduation to live."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SessionDuration = Literal["1d", "5d", "20d", "60d"]

DURATION_TRADING_DAYS: dict[SessionDuration, int] = {
    "1d": 1,
    "5d": 5,
    "20d": 20,
    "60d": 60,
}


@dataclass(frozen=True)
class PaperSessionPlan:
    duration: SessionDuration
    trading_days: int
    auto_graduate_to_live: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "duration": self.duration,
            "trading_days": self.trading_days,
            "auto_graduate_to_live": False,
            "description": self.description,
        }


def plan_for(duration: SessionDuration | str) -> PaperSessionPlan:
    key = str(duration).strip().lower()
    if key not in DURATION_TRADING_DAYS:
        raise ValueError(f"unsupported_duration:{duration}")
    days = DURATION_TRADING_DAYS[key]  # type: ignore[index]
    return PaperSessionPlan(
        duration=key,  # type: ignore[arg-type]
        trading_days=days,
        auto_graduate_to_live=False,
        description=f"Controlled paper session for {days} trading day(s); live graduation disabled.",
    )


def bars_for_duration(duration: SessionDuration | str, *, bars_per_day: int = 1) -> int:
    """Approximate bar budget for simulated streams (daily bars default)."""
    return plan_for(duration).trading_days * bars_per_day

"""Walk-forward window generation (no backward leakage)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from quantfund.data.models import MarketBar
from quantfund.research.splits import Period


class WalkForwardConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    train_sessions: int = 3
    validation_sessions: int = 1
    test_sessions: int = 1
    step_sessions: int = 1
    mode: str = "rolling"  # rolling | expanding
    anchored: bool = False


@dataclass(frozen=True)
class WalkForwardWindow:
    index: int
    train: Period
    validation: Period
    test: Period
    train_bars: list[MarketBar]
    validation_bars: list[MarketBar]
    test_bars: list[MarketBar]


def _session_dates(bars: list[MarketBar]) -> list[date]:
    return sorted(
        {
            b.timestamp.date() if isinstance(b.timestamp, datetime) else b.timestamp
            for b in bars
        }
    )


def _slice_bars(bars: list[MarketBar], d0: date, d1: date) -> list[MarketBar]:
    out: list[MarketBar] = []
    for b in bars:
        d = b.timestamp.date() if isinstance(b.timestamp, datetime) else b.timestamp
        if d0 <= d <= d1:
            out.append(b)
    return out


def generate_walkforward_windows(
    bars: list[MarketBar],
    config: WalkForwardConfig,
) -> list[WalkForwardWindow]:
    """Generate chronological walk-forward windows.

    Later windows never appear in earlier train/validation sets.
    """
    if config.mode not in {"rolling", "expanding"}:
        raise ValueError("mode must be rolling or expanding")
    dates = _session_dates(bars)
    need = config.train_sessions + config.validation_sessions + config.test_sessions
    windows: list[WalkForwardWindow] = []
    origin = 0
    idx = 0
    expanding = config.mode == "expanding" or config.anchored

    while origin + need <= len(dates):
        if expanding:
            t0 = 0
            t1 = origin + config.train_sessions - 1
        else:
            t0 = origin
            t1 = origin + config.train_sessions - 1
        v0 = t1 + 1
        v1 = v0 + config.validation_sessions - 1
        te0 = v1 + 1
        te1 = te0 + config.test_sessions - 1
        if te1 >= len(dates):
            break
        if not (t1 < v0 <= v1 < te0 <= te1):
            raise RuntimeError("invalid walk-forward indices")

        train_p = Period(start=dates[t0], end=dates[t1])
        val_p = Period(start=dates[v0], end=dates[v1])
        test_p = Period(start=dates[te0], end=dates[te1])
        windows.append(
            WalkForwardWindow(
                index=idx,
                train=train_p,
                validation=val_p,
                test=test_p,
                train_bars=_slice_bars(bars, train_p.start, train_p.end),
                validation_bars=_slice_bars(bars, val_p.start, val_p.end),
                test_bars=_slice_bars(bars, test_p.start, test_p.end),
            )
        )
        idx += 1
        origin += config.step_sessions
    return windows

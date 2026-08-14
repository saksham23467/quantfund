"""Deterministic replay of recorded market events through PaperSession."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.models import MarketDataEvent, PaperSessionConfig
from quantfund.paper.risk import PaperRiskConfig
from quantfund.paper.session import PaperSession, PaperSessionResult
from quantfund.strategies.base import Strategy


@dataclass
class ReplayResult:
    first: PaperSessionResult
    second: PaperSessionResult
    deterministic: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "deterministic": self.deterministic,
            "first_state_hash": self.first.state_hash,
            "second_state_hash": self.second.state_hash,
        }


def run_paper_session(
    *,
    config: PaperSessionConfig,
    strategy: Strategy,
    events: list[MarketDataEvent],
    calendar: CalendarProvider | None = None,
    instruments: list[Instrument] | None = None,
    risk_config: PaperRiskConfig | None = None,
    audit_path: Path | None = None,
    strategy_factory: Callable[[], Strategy] | None = None,
) -> PaperSessionResult:
    """Run a single paper session over an event stream."""
    strat = strategy_factory() if strategy_factory else strategy
    session = PaperSession(
        config,
        strategy=strat,
        calendar=calendar,
        instruments=instruments,
        risk_config=risk_config,
        audit_path=audit_path,
    )
    session.start()
    for ev in events:
        session.process_event(ev)
        if session.halted:
            break
    return session.stop()


def replay_deterministic(
    *,
    config: PaperSessionConfig,
    strategy_factory: Callable[[], Strategy],
    events: list[MarketDataEvent],
    calendar: CalendarProvider | None = None,
    instruments: list[Instrument] | None = None,
    risk_config: PaperRiskConfig | None = None,
) -> ReplayResult:
    """Run twice with fresh strategy instances; compare state hashes."""
    first = run_paper_session(
        config=config,
        strategy=strategy_factory(),
        events=events,
        calendar=calendar,
        instruments=instruments,
        risk_config=risk_config,
        strategy_factory=None,
    )
    second = run_paper_session(
        config=config,
        strategy=strategy_factory(),
        events=events,
        calendar=calendar,
        instruments=instruments,
        risk_config=risk_config,
        strategy_factory=None,
    )
    return ReplayResult(
        first=first,
        second=second,
        deterministic=first.state_hash == second.state_hash,
    )

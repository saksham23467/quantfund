"""UNKNOWN universe membership must not generate trades."""

from __future__ import annotations

from datetime import date, datetime

from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.data.models import MarketBar
from quantfund.data.universe.membership import MembershipAnswer, was_member
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseVersion,
)
from quantfund.strategies.baselines.momentum import MomentumStrategy
from quantfund.strategies.base import StrategyContext


def test_was_member_unknown_off_asof():
    u = UniverseVersion(
        universe_id="nifty50",
        universe_version="t",
        completeness=UniverseCompleteness.CURRENT_SNAPSHOT_ONLY,
        as_of_date=date(2024, 1, 8),
        source="t",
        members=[UniverseMember(instrument_id="NSE:TEST", symbol="TEST")],
    )
    assert was_member(u, symbol="TEST", on=date(2024, 1, 2)) == MembershipAnswer.UNKNOWN


def test_unknown_membership_blocks_orders():
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, d),
            symbol="TEST",
            open=100,
            high=115,
            low=99,
            close=110,
            volume=100,
        )
        for d in (2, 3, 4, 5, 8)
    ]
    strat = MomentumStrategy(symbol="TEST", lookback=1, threshold=-1.0)

    def enrich(ctx: StrategyContext) -> StrategyContext:
        ctx.membership = "UNKNOWN"
        return ctx

    engine = BacktestEngine(
        strat,
        config=BacktestConfig(initial_capital=100_000),
        context_enricher=enrich,
    )
    result = engine.run(bars)
    assert result.portfolio.fills == []

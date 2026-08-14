"""StrategySpec validation and interpreter (no arbitrary code)."""

from __future__ import annotations

from datetime import datetime

import pytest

from quantfund.data.models import MarketBar
from quantfund.strategies.base import StrategyContext
from quantfund.strategies.spec.interpret import interpret_strategy_spec
from quantfund.strategies.spec.models import FeatureRef, Rule, StrategySpec
from quantfund.strategies.spec.validate import ValidationError, validate_strategy_spec
from quantfund.trading.models import SignalAction


def test_rejects_unknown_feature_and_banned_tokens():
    with pytest.raises(ValidationError):
        validate_strategy_spec(
            StrategySpec(
                name="bad",
                universe_id="nifty50",
                symbol="TEST",
                features=[FeatureRef(feature_name="not_a_real_feature")],
                entry_rules=[Rule(op="gt", left="feature:x", right=0)],
            )
        )
    with pytest.raises(ValidationError):
        validate_strategy_spec(
            StrategySpec(
                name="evil",
                universe_id="nifty50",
                symbol="TEST",
                hypothesis="import os",
                features=[FeatureRef(feature_name="sma", params={"window": 3})],
                entry_rules=[Rule(op="gt", left="feature:sma_3", right=0)],
            )
        )


def test_interpreter_deterministic_signal():
    spec = StrategySpec(
        name="mom_spec",
        universe_id="nifty50",
        symbol="TEST",
        features=[FeatureRef(feature_name="momentum", params={"window": 2})],
        entry_rules=[Rule(op="gt", left="feature:momentum_2", right=0.0)],
        exit_rules=[Rule(op="lte", left="feature:momentum_2", right=0.0)],
    )
    strat = interpret_strategy_spec(spec)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, d),
            symbol="TEST",
            open=100,
            high=100 + d + 1,
            low=99,
            close=100 + d,
            volume=1,
        )
        for d in (2, 3, 4)
    ]
    ctx = StrategyContext(
        timestamp=bars[-1].timestamp,
        symbol="TEST",
        history=bars,
        position_quantity=0,
        cash=100_000,
        features={"momentum_2": 0.05},
        membership="TRUE",
    )
    sig = strat.generate_signal(ctx)
    assert sig.action == SignalAction.BUY

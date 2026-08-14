"""Phase 4 Expr AST + Rule compatibility + interpreter safety."""

from __future__ import annotations

from datetime import datetime

import pytest

from quantfund.strategies.base import StrategyContext
from quantfund.strategies.spec.expr import Expr
from quantfund.strategies.spec.interpret import (
    evaluate_expr,
    evaluate_rule,
    interpret_strategy_spec,
)
from quantfund.strategies.spec.models import FeatureRef, Rule, StrategySpec
from quantfund.strategies.spec.validate import ValidationError, validate_strategy_spec
from quantfund.trading.models import SignalAction


FEATS = {
    "sma_20": 100.0,
    "sma_50": 90.0,
    "roc_20": 0.05,
    "momentum_2": 0.02,
    "rolling_vol_20": 0.01,
}


def test_expr_constant_and_feature_ref():
    assert evaluate_expr(Expr(op="constant", value=2.0), {}) == 2.0
    assert evaluate_expr(Expr(op="feature_ref", name="sma_20"), FEATS) == 100.0
    assert evaluate_expr(Expr(op="feature_ref", name="missing"), FEATS) is None


def test_expr_arithmetic_ops():
    a = Expr(op="constant", value=10.0)
    b = Expr(op="constant", value=3.0)
    assert evaluate_expr(Expr(op="add", args=[a, b]), {}) == 13.0
    assert evaluate_expr(Expr(op="subtract", args=[a, b]), {}) == 7.0
    assert evaluate_expr(Expr(op="multiply", args=[a, b]), {}) == 30.0
    assert evaluate_expr(Expr(op="divide", args=[a, b]), {}) == pytest.approx(10 / 3)
    assert evaluate_expr(Expr(op="abs", args=[Expr(op="constant", value=-4.0)]), {}) == 4.0
    assert evaluate_expr(Expr(op="min", args=[a, b]), {}) == 3.0
    assert evaluate_expr(Expr(op="max", args=[a, b]), {}) == 10.0


def test_expr_divide_by_zero_returns_none():
    expr = Expr(
        op="divide",
        args=[Expr(op="constant", value=1.0), Expr(op="constant", value=0.0)],
    )
    assert evaluate_expr(expr, {}) is None


def test_expr_if_conditional():
    expr = Expr(
        op="if",
        condition=Rule(op="gt", left="feature:roc_20", right=0.0),
        then=Expr(op="constant", value=1.0),
        **{"else": Expr(op="constant", value=0.0)},
    )
    assert evaluate_expr(expr, FEATS) == 1.0
    assert evaluate_expr(expr, {"roc_20": -0.1}) == 0.0


def test_nested_expressions():
    expr = Expr(
        op="add",
        args=[
            Expr(
                op="subtract",
                args=[
                    Expr(op="feature_ref", name="sma_20"),
                    Expr(op="feature_ref", name="sma_50"),
                ],
            ),
            Expr(op="constant", value=0.05),
        ],
    )
    assert evaluate_expr(expr, FEATS) == pytest.approx(10.05)


def test_legacy_rule_still_works():
    rule = Rule(op="gt", left="feature:sma_20", right="feature:sma_50")
    assert evaluate_rule(rule, FEATS) is True
    validate_strategy_spec(
        StrategySpec(
            name="legacy",
            universe_id="nifty50",
            symbol="TEST",
            features=[FeatureRef(feature_name="sma", params={"window": 20})],
            entry_rules=[rule],
        )
    )


def test_rule_with_expr_operands():
    rule = Rule(
        op="gt",
        left=Expr(
            op="add",
            args=[
                Expr(op="feature_ref", name="sma_20"),
                Expr(op="constant", value=1.0),
            ],
        ),
        right=Expr(op="feature_ref", name="sma_50"),
    )
    assert evaluate_rule(rule, FEATS) is True


def test_nested_boolean_rules():
    rule = Rule(
        op="and",
        args=[
            Rule(op="gt", left="feature:momentum_2", right=0.0),
            Rule(op="lt", left="feature:rolling_vol_20", right=0.05),
        ],
    )
    assert evaluate_rule(rule, FEATS) is True


def test_invalid_expr_shape_rejected():
    with pytest.raises(Exception):
        Expr(op="add", args=[Expr(op="constant", value=1.0)])  # needs 2 args


def test_arithmetic_as_rule_op_rejected_via_schema():
    with pytest.raises(Exception):
        Rule(op="add", left=1, right=2)  # type: ignore[arg-type]


def test_invalid_feature_holds():
    strat = interpret_strategy_spec(
        StrategySpec(
            name="hold_missing",
            universe_id="nifty50",
            symbol="TEST",
            features=[FeatureRef(feature_name="momentum", params={"window": 2})],
            entry_rules=[Rule(op="gt", left="feature:momentum_2", right=0.0)],
        )
    )
    ctx = StrategyContext(
        timestamp=datetime(2024, 1, 4),
        symbol="TEST",
        history=[],
        position_quantity=0,
        cash=100_000,
        features={"momentum_2": None},
        membership="TRUE",
    )
    assert strat.generate_signal(ctx).action == SignalAction.HOLD


def test_zero_division_holds():
    strat = interpret_strategy_spec(
        StrategySpec(
            name="div0",
            universe_id="nifty50",
            symbol="TEST",
            features=[FeatureRef(feature_name="sma", params={"window": 3})],
            entry_rules=[
                Rule(
                    op="gt",
                    left=Expr(
                        op="divide",
                        args=[
                            Expr(op="feature_ref", name="sma_3"),
                            Expr(op="constant", value=0.0),
                        ],
                    ),
                    right=Expr(op="constant", value=0.0),
                )
            ],
        )
    )
    ctx = StrategyContext(
        timestamp=datetime(2024, 1, 4),
        symbol="TEST",
        history=[],
        position_quantity=0,
        cash=100_000,
        features={"sma_3": 10.0},
        membership="TRUE",
    )
    assert strat.generate_signal(ctx).action == SignalAction.HOLD


def test_interpreter_determinism():
    from quantfund.data.models import MarketBar

    spec = StrategySpec(
        name="det",
        universe_id="nifty50",
        symbol="TEST",
        features=[FeatureRef(feature_name="momentum", params={"window": 2})],
        entry_rules=[Rule(op="gt", left="feature:momentum_2", right=0.0)],
        exit_rules=[Rule(op="lte", left="feature:momentum_2", right=0.0)],
    )
    s1 = interpret_strategy_spec(spec)
    s2 = interpret_strategy_spec(spec)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, d),
            symbol="TEST",
            open=100.0 + d,
            high=101.0 + d,
            low=99.0 + d,
            close=100.5 + d,
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
    assert s1.generate_signal(ctx).action == s2.generate_signal(ctx).action == SignalAction.BUY

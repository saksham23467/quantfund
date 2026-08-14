"""Phase 4 structured validator + malicious payload rejection."""

from __future__ import annotations

import math

import pytest

from quantfund.strategies.spec.dsl import ComplexityLimits
from quantfund.strategies.spec.expr import Expr
from quantfund.strategies.spec.models import FeatureRef, Rule, StrategySpec
from quantfund.strategies.spec.validate import ValidationError, validate_strategy_spec
from quantfund.strategies.spec.validator import StrategySpecValidator


def _base(**kwargs) -> StrategySpec:
    data = dict(
        name="ok",
        universe_id="nifty50",
        symbol="TEST",
        features=[FeatureRef(feature_name="momentum", params={"window": 2})],
        entry_rules=[Rule(op="gt", left="feature:momentum_2", right=0.0)],
    )
    data.update(kwargs)
    return StrategySpec(**data)


def test_structured_validator_valid():
    result = StrategySpecValidator().validate(_base())
    assert result.valid is True
    assert result.to_dict()["status"] == "VALID"


def test_unknown_feature_structured():
    result = StrategySpecValidator().validate(
        _base(features=[FeatureRef(feature_name="not_real")])
    )
    assert result.valid is False
    assert any(e.code == "unknown_feature" for e in result.errors)


def test_unknown_operator_rejected_by_schema():
    with pytest.raises(Exception):
        Rule(op="eval", left=1, right=2)  # type: ignore[arg-type]


def test_invalid_parameter_window():
    with pytest.raises(ValidationError):
        validate_strategy_spec(
            _base(features=[FeatureRef(feature_name="sma", params={"window": -1})])
        )


def test_excessive_depth():
    deep = Rule(op="gt", left="feature:momentum_2", right=0.0)
    for _ in range(12):
        deep = Rule(op="not", args=[deep])
    with pytest.raises(ValidationError, match="deep"):
        validate_strategy_spec(_base(entry_rules=[deep]))


def test_excessive_nodes():
    # Build a wide expression tree
    leaves = [Expr(op="constant", value=1.0) for _ in range(40)]
    # nest adds pairwise
    nodes = leaves
    while len(nodes) > 1:
        nxt = []
        for i in range(0, len(nodes) - 1, 2):
            nxt.append(Expr(op="add", args=[nodes[i], nodes[i + 1]]))
        if len(nodes) % 2 == 1:
            nxt.append(nodes[-1])
        nodes = nxt
    expr = nodes[0]
    limits = ComplexityLimits(max_expression_nodes=20)
    with pytest.raises(ValidationError, match="node count"):
        validate_strategy_spec(
            _base(
                entry_rules=[
                    Rule(op="gt", left=expr, right=Expr(op="constant", value=0.0))
                ]
            ),
            limits=limits,
        )


def test_excessive_rules_and_features():
    limits = ComplexityLimits(max_rules=2, max_features=1)
    with pytest.raises(ValidationError, match="features"):
        validate_strategy_spec(
            _base(
                features=[
                    FeatureRef(feature_name="sma", params={"window": 3}),
                    FeatureRef(feature_name="ema", params={"window": 3}),
                ]
            ),
            limits=limits,
        )
    with pytest.raises(ValidationError, match="rules"):
        validate_strategy_spec(
            _base(
                entry_rules=[
                    Rule(op="gt", left="feature:momentum_2", right=0.0),
                    Rule(op="gt", left="feature:momentum_2", right=0.1),
                ],
                exit_rules=[Rule(op="lt", left="feature:momentum_2", right=0.0)],
            ),
            limits=limits,
        )


def test_nan_and_infinity_rejected():
    with pytest.raises(ValidationError):
        validate_strategy_spec(
            _base(
                entry_rules=[
                    Rule(
                        op="gt",
                        left=Expr(op="constant", value=float("nan")),
                        right=Expr(op="constant", value=0.0),
                    )
                ]
            )
        )
    with pytest.raises(ValidationError):
        validate_strategy_spec(
            _base(
                entry_rules=[
                    Rule(
                        op="gt",
                        left=Expr(op="constant", value=float("inf")),
                        right=Expr(op="constant", value=0.0),
                    )
                ]
            )
        )


@pytest.mark.parametrize(
    "payload",
    [
        "eval(1)",
        "exec('x')",
        "__import__('os')",
        "os.system('id')",
        "subprocess.Popen",
        "open('/etc/passwd')",
        "socket.connect",
        "import os",
    ],
)
def test_malicious_tokens_rejected(payload: str):
    with pytest.raises(ValidationError, match="forbidden"):
        validate_strategy_spec(_base(hypothesis=payload))


def test_self_acceptance_metadata_rejected():
    result = StrategySpecValidator().validate(
        _base(metadata={"accepted_for_validation_pipeline": True})
    )
    assert result.valid is False
    assert any(e.code == "self_acceptance_forbidden" for e in result.errors)


def test_raising_validator_still_works():
    with pytest.raises(ValidationError):
        validate_strategy_spec(_base(features=[FeatureRef(feature_name="nope")]))

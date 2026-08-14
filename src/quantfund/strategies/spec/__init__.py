"""Structured StrategySpec (no arbitrary code execution)."""

from quantfund.strategies.spec.expr import Expr
from quantfund.strategies.spec.interpret import (
    evaluate_expr,
    evaluate_rule,
    interpret_strategy_spec,
)
from quantfund.strategies.spec.models import FeatureRef, Rule, StrategySpec
from quantfund.strategies.spec.validate import ValidationError, validate_strategy_spec
from quantfund.strategies.spec.validator import (
    SpecValidationIssue,
    StrategySpecValidationResult,
    StrategySpecValidator,
)

__all__ = [
    "Expr",
    "FeatureRef",
    "Rule",
    "StrategySpec",
    "ValidationError",
    "validate_strategy_spec",
    "StrategySpecValidator",
    "StrategySpecValidationResult",
    "SpecValidationIssue",
    "interpret_strategy_spec",
    "evaluate_expr",
    "evaluate_rule",
]

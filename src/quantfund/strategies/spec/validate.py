"""Validate StrategySpec against allowlists — reject unsafe constructs.

Phase 2 API: ``validate_strategy_spec`` raises ``ValidationError``.
Phase 4 structured API lives in ``validator.py`` and wraps the same rules.
"""

from __future__ import annotations

import math

from quantfund.strategies.spec.dsl import (
    ALLOWED_FEATURE_NAMES,
    ALLOWED_RULE_OPS,
    BANNED_TOKENS,
    DEFAULT_COMPLEXITY_LIMITS,
    ComplexityLimits,
)
from quantfund.strategies.spec.expr import Expr
from quantfund.strategies.spec.models import Operand, Rule, StrategySpec

# Backward-compatible alias used by older imports/tests
ALLOWED_OPS = ALLOWED_RULE_OPS


class ValidationError(ValueError):
    pass


def _is_finite_number(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _validate_expr(expr: Expr, *, depth: int, limits: ComplexityLimits, node_count: list[int]) -> None:
    node_count[0] += 1
    if node_count[0] > limits.max_expression_nodes:
        raise ValidationError("expression node count exceeds limit")
    if depth > limits.max_expr_depth:
        raise ValidationError("expression nesting too deep")
    if expr.op == "constant":
        if expr.value is None or not _is_finite_number(expr.value):
            raise ValidationError("constant must be a finite number")
        return
    if expr.op == "feature_ref":
        if not expr.name or not str(expr.name).strip():
            raise ValidationError("feature_ref requires name")
        # Output column names like sma_20 are allowed; base name checked loosely
        return
    if expr.op == "if":
        from quantfund.strategies.spec.models import Rule as RuleModel

        if not isinstance(expr.condition, RuleModel):
            # pydantic may leave dict — try coerce
            try:
                cond = RuleModel.model_validate(expr.condition)
            except Exception as exc:  # noqa: BLE001
                raise ValidationError("if.condition must be a Rule") from exc
        else:
            cond = expr.condition
        _validate_rule(cond, depth=depth + 1, limits=limits, node_count=node_count)
        assert expr.then is not None and expr.else_ is not None
        _validate_expr(expr.then, depth=depth + 1, limits=limits, node_count=node_count)
        _validate_expr(expr.else_, depth=depth + 1, limits=limits, node_count=node_count)
        return
    for child in expr.args:
        _validate_expr(child, depth=depth + 1, limits=limits, node_count=node_count)


def _validate_operand(
    side: Operand,
    *,
    depth: int,
    limits: ComplexityLimits,
    node_count: list[int],
) -> None:
    if side is None or isinstance(side, (int, float)):
        if isinstance(side, float) and not math.isfinite(side):
            raise ValidationError("non-finite numeric operand")
        return
    if isinstance(side, str):
        if side.startswith("feature:"):
            return
        raise ValidationError(f"invalid rule operand: {side!r}")
    if isinstance(side, Expr):
        _validate_expr(side, depth=depth, limits=limits, node_count=node_count)
        return
    raise ValidationError(f"invalid rule operand: {side!r}")


def _validate_rule(
    rule: Rule,
    depth: int = 0,
    *,
    limits: ComplexityLimits | None = None,
    node_count: list[int] | None = None,
) -> None:
    limits = limits or DEFAULT_COMPLEXITY_LIMITS
    node_count = node_count if node_count is not None else [0]
    if depth > limits.max_rule_depth:
        raise ValidationError("rule nesting too deep")
    if rule.op not in ALLOWED_RULE_OPS:
        raise ValidationError(f"op not allowlisted: {rule.op}")
    # Arithmetic must never appear as a Rule op
    if rule.op in {
        "add",
        "subtract",
        "multiply",
        "divide",
        "abs",
        "min",
        "max",
        "constant",
        "feature_ref",
        "if",
    }:
        raise ValidationError(f"arithmetic/value op not allowed as Rule: {rule.op}")
    if rule.op in {"and", "or"}:
        if not rule.args:
            raise ValidationError(f"{rule.op} requires args")
        for child in rule.args:
            _validate_rule(child, depth + 1, limits=limits, node_count=node_count)
        return
    if rule.op == "not":
        if len(rule.args) != 1:
            raise ValidationError("not requires exactly one arg")
        _validate_rule(rule.args[0], depth + 1, limits=limits, node_count=node_count)
        return
    _validate_operand(rule.left, depth=depth + 1, limits=limits, node_count=node_count)
    _validate_operand(rule.right, depth=depth + 1, limits=limits, node_count=node_count)


def validate_strategy_spec(
    spec: StrategySpec,
    *,
    limits: ComplexityLimits | None = None,
) -> StrategySpec:
    """Phase 2-compatible raising validator (extended for Expr operands)."""
    limits = limits or DEFAULT_COMPLEXITY_LIMITS
    if not spec.name.strip():
        raise ValidationError("name required")
    if len(spec.name) > limits.max_name_length:
        raise ValidationError("name too long")
    if not spec.symbol.strip():
        raise ValidationError("symbol required")
    if not spec.entry_rules:
        raise ValidationError("entry_rules required")
    if len(spec.hypothesis) > limits.max_hypothesis_length:
        raise ValidationError("hypothesis too long")
    if len(spec.features) > limits.max_features:
        raise ValidationError("too many features")
    if len(spec.entry_rules) + len(spec.exit_rules) > limits.max_rules:
        raise ValidationError("too many rules")
    if len(spec.parameters) > limits.max_parameters:
        raise ValidationError("too many parameters")

    for fr in spec.features:
        if fr.feature_name not in ALLOWED_FEATURE_NAMES:
            raise ValidationError(f"feature not allowlisted: {fr.feature_name}")
        if "window" in fr.params:
            w = fr.params["window"]
            if not isinstance(w, int) or isinstance(w, bool) or w < 1:
                raise ValidationError(f"invalid window for {fr.feature_name}")

    node_count = [0]
    for rule in spec.entry_rules + spec.exit_rules:
        _validate_rule(rule, limits=limits, node_count=node_count)

    if not 0 < spec.position_sizing.fraction <= 1:
        raise ValidationError("position_sizing.fraction must be in (0,1]")
    if spec.position_sizing.method not in {"fixed_fraction"}:
        raise ValidationError("unsupported position sizing method")
    if spec.risk_constraints.max_allocation > 1:
        raise ValidationError("risk_constraints cannot exceed 100% allocation")
    if spec.risk_constraints.max_allocation <= 0:
        raise ValidationError("risk_constraints.max_allocation must be positive")

    blob = spec.model_dump_json()
    for banned in BANNED_TOKENS:
        if banned in blob:
            raise ValidationError(f"forbidden token in StrategySpec: {banned}")
    return spec

"""Deterministic StrategySpec interpreter (no eval/exec/imports)."""

from __future__ import annotations

import math
from typing import Any

from quantfund.data.models import MarketBar
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.strategies.baselines._sizing import buy_shares, hold, sell_all
from quantfund.strategies.spec.expr import Expr
from quantfund.strategies.spec.models import Operand, Rule, StrategySpec
from quantfund.strategies.spec.validate import validate_strategy_spec
from quantfund.trading.models import Signal


def evaluate_expr(expr: Expr, features: dict[str, float | None]) -> float | None:
    """Evaluate a value expression. Returns None on invalid / non-finite results."""
    op = expr.op
    if op == "constant":
        if expr.value is None or not math.isfinite(float(expr.value)):
            return None
        return float(expr.value)
    if op == "feature_ref":
        if not expr.name:
            return None
        val = features.get(expr.name)
        if val is None or not math.isfinite(float(val)):
            return None
        return float(val)
    if op == "abs":
        a = evaluate_expr(expr.args[0], features)
        return None if a is None else abs(a)
    if op == "if":
        from quantfund.strategies.spec.models import Rule as RuleModel

        cond = expr.condition
        if not isinstance(cond, RuleModel):
            try:
                cond = RuleModel.model_validate(cond)
            except Exception:  # noqa: BLE001
                return None
        branch = expr.then if evaluate_rule(cond, features) else expr.else_
        if branch is None:
            return None
        return evaluate_expr(branch, features)

    # Binary / n-ary arithmetic — explicit dispatch only
    values: list[float] = []
    for child in expr.args:
        v = evaluate_expr(child, features)
        if v is None or not math.isfinite(v):
            return None
        values.append(v)

    if op == "add":
        return float(sum(values))
    if op == "subtract":
        out = values[0]
        for v in values[1:]:
            out -= v
        return float(out)
    if op == "multiply":
        out = 1.0
        for v in values:
            out *= v
        return float(out)
    if op == "divide":
        out = values[0]
        for v in values[1:]:
            if v == 0.0:
                return None  # never create infinity
            out /= v
        if not math.isfinite(out):
            return None
        return float(out)
    if op == "min":
        return float(min(values))
    if op == "max":
        return float(max(values))
    return None


def _resolve_operand(operand: Operand, features: dict[str, float | None]) -> float | None:
    """Resolve legacy string/number or Expr operand."""
    if operand is None:
        return None
    if isinstance(operand, bool):
        return None
    if isinstance(operand, (int, float)):
        if not math.isfinite(float(operand)):
            return None
        return float(operand)
    if isinstance(operand, str) and operand.startswith("feature:"):
        key = operand.split("feature:", 1)[1]
        val = features.get(key)
        if val is None or not math.isfinite(float(val)):
            return None
        return float(val)
    if isinstance(operand, Expr):
        return evaluate_expr(operand, features)
    return None


def evaluate_rule(rule: Rule, features: dict[str, float | None]) -> bool:
    """Boolean predicate evaluation — never executes arbitrary code."""
    if rule.op == "and":
        return all(evaluate_rule(r, features) for r in rule.args)
    if rule.op == "or":
        return any(evaluate_rule(r, features) for r in rule.args)
    if rule.op == "not":
        return not evaluate_rule(rule.args[0], features)

    left = _resolve_operand(rule.left, features)
    right = _resolve_operand(rule.right, features)
    if left is None or right is None:
        return False
    if rule.op == "gt":
        return left > right
    if rule.op == "gte":
        return left >= right
    if rule.op == "lt":
        return left < right
    if rule.op == "lte":
        return left <= right
    if rule.op == "eq":
        return left == right
    return False


# Backward-compatible aliases
def _resolve(operand: str | float | None, features: dict[str, float | None]) -> float | None:
    return _resolve_operand(operand, features)


def eval_rule(rule: Rule, features: dict[str, float | None]) -> bool:
    return evaluate_rule(rule, features)


class SpecInterpretedStrategy(Strategy):
    """Executable strategy produced from a validated StrategySpec."""

    def __init__(self, spec: StrategySpec) -> None:
        self.spec = validate_strategy_spec(spec)

    def metadata(self) -> StrategyMetadata:
        version = self.spec.version or str(self.spec.metadata.get("version", "1.0.0"))
        return StrategyMetadata(
            strategy_id=self.spec.effective_strategy_id(),
            strategy_name=self.spec.name,
            strategy_version=version,
            parameters=dict(self.spec.parameters),
            description=self.spec.hypothesis,
            required_features=[
                (
                    f"{fr.feature_name}_{fr.params['window']}"
                    if "window" in fr.params
                    else fr.feature_name
                )
                for fr in self.spec.features
            ],
        )

    def prepare_data(self, bars: list[MarketBar]) -> list[MarketBar]:
        return [b for b in bars if b.symbol == self.spec.symbol]

    def generate_signal(self, context: StrategyContext) -> Signal:
        if context.membership == "UNKNOWN":
            return hold(context, self.spec.symbol, reason="membership_unknown")
        if context.membership == "FALSE":
            return hold(context, self.spec.symbol, reason="not_in_universe")
        feats = context.features or {}
        try:
            enter = any(evaluate_rule(r, feats) for r in self.spec.entry_rules)
            exit_ = (
                any(evaluate_rule(r, feats) for r in self.spec.exit_rules)
                if self.spec.exit_rules
                else False
            )
        except Exception:  # noqa: BLE001 — never crash into execution; HOLD
            return hold(context, self.spec.symbol, reason="expr_eval_error")
        frac = min(self.spec.position_sizing.fraction, self.spec.risk_constraints.max_allocation)
        if enter and context.position_quantity <= 0:
            return buy_shares(context, self.spec.symbol, frac)
        if exit_ and context.position_quantity > 0:
            return sell_all(context, self.spec.symbol)
        return hold(context, self.spec.symbol)


def interpret_strategy_spec(spec: StrategySpec | dict[str, Any]) -> SpecInterpretedStrategy:
    if isinstance(spec, dict):
        spec = StrategySpec.model_validate(spec)
    return SpecInterpretedStrategy(spec)

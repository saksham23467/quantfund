"""Allowlists and complexity defaults for StrategySpec DSL."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# Feature library names (base names; windowed outputs like sma_20 are derived)
ALLOWED_FEATURE_NAMES = frozenset(
    {
        "return_1",
        "log_return_1",
        "rolling_return",
        "sma",
        "ema",
        "momentum",
        "roc",
        "rolling_vol",
        "atr",
        "realized_vol",
        "volume_change",
        "relative_volume",
        "dist_to_sma",
        "zscore",
        "benchmark_return",
        "relative_strength",
    }
)

ALLOWED_RULE_OPS = frozenset({"gt", "gte", "lt", "lte", "eq", "and", "or", "not"})

ALLOWED_EXPR_OPS = frozenset(
    {
        "constant",
        "feature_ref",
        "add",
        "subtract",
        "multiply",
        "divide",
        "abs",
        "min",
        "max",
        "if",
    }
)

ALLOWED_SIZING_METHODS = frozenset({"fixed_fraction"})

PLATFORM_MAX_ALLOCATION = 1.0

# Tokens that must never appear in serialized specs (defense in depth)
BANNED_TOKENS = (
    "__",
    "import ",
    "eval(",
    "exec(",
    "compile(",
    "open(",
    "os.",
    "subprocess",
    "socket",
    "system(",
    "__import__",
    "builtins",
    "getattr(",
    "globals(",
    "locals(",
    "memoryview(",
)


class ComplexityLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_rule_depth: int = 8
    max_expr_depth: int = 8
    max_rules: int = 16
    max_features: int = 12
    max_parameters: int = 24
    max_expression_nodes: int = 64
    max_hypothesis_length: int = 2000
    max_name_length: int = 128


DEFAULT_COMPLEXITY_LIMITS = ComplexityLimits()

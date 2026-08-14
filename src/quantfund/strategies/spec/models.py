"""JSON StrategySpec schema — AI-safe structured hypotheses.

Phase 2 Rule predicates remain backward compatible.
Phase 4 adds optional Expr operands and identity/metadata fields.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantfund.strategies.spec.expr import Expr


Operand = str | float | Expr | None


class FeatureRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    feature_name: str
    version: str = "1.0.0"
    params: dict[str, Any] = Field(default_factory=dict)


class Rule(BaseModel):
    """Allowlisted boolean predicate. No code execution.

    Comparison operands may be:
    - legacy strings (``feature:sma_20``) or numbers  [Phase 2]
    - Expr value nodes                               [Phase 4]
    """

    model_config = ConfigDict(frozen=True)

    op: Literal["gt", "gte", "lt", "lte", "eq", "and", "or", "not"]
    left: Operand = None
    right: Operand = None
    args: list[Rule] = Field(default_factory=list)


# Resolve Expr.condition forward reference to Rule
Expr.model_rebuild(_types_namespace={"Rule": Rule, "Expr": Expr})


class SizingSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: Literal["fixed_fraction"] = "fixed_fraction"
    fraction: float = 0.95


class RiskSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Cannot raise platform ceilings; these are strategy-side preferences only
    max_allocation: float = 0.95


class StrategySpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    hypothesis: str = ""
    universe_id: str
    symbol: str
    strategy_id: str | None = None
    version: str = "1.0.0"
    features: list[FeatureRef] = Field(default_factory=list)
    entry_rules: list[Rule] = Field(default_factory=list)
    exit_rules: list[Rule] = Field(default_factory=list)
    position_sizing: SizingSpec = Field(default_factory=SizingSpec)
    risk_constraints: RiskSpec = Field(default_factory=RiskSpec)
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("strategy_id", mode="before")
    @classmethod
    def empty_id_to_none(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        return v

    def effective_strategy_id(self) -> str:
        return self.strategy_id or f"spec:{self.name}"

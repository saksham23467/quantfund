"""Generation request and pipeline result models (research-safe inputs only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from quantfund.strategies.spec.dsl import ComplexityLimits, DEFAULT_COMPLEXITY_LIMITS
from quantfund.strategies.spec.models import RiskSpec, SizingSpec, StrategySpec


class GenerationRequest(BaseModel):
    """Inputs the generator may see. Must never include TEST results or acceptance."""

    model_config = ConfigDict(frozen=True)

    universe_id: str = "nifty50"
    symbol: str = "TEST"
    allowed_features: list[str] = Field(
        default_factory=lambda: ["momentum", "sma", "roc", "rolling_vol", "zscore"]
    )
    allowed_operators: list[str] = Field(
        default_factory=lambda: [
            "gt",
            "gte",
            "lt",
            "lte",
            "eq",
            "and",
            "or",
            "not",
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
        ]
    )
    maximum_complexity: ComplexityLimits = Field(default_factory=lambda: DEFAULT_COMPLEXITY_LIMITS)
    maximum_rules: int = 8
    maximum_features: int = 6
    allowed_position_sizing: SizingSpec = Field(default_factory=SizingSpec)
    risk_constraints: RiskSpec = Field(default_factory=RiskSpec)
    number_of_candidates: int = 20
    random_seed: int = 42
    research_objective: str = "exploratory_hypothesis_generation"
    family_id: str = "ai_factory_default"
    include_malformed_fixtures: bool = True
    generator_model: str = "mock_v1"
    prompt_id: str = "mock_prompt_v1"


class GeneratorMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    generator_type: Literal["mock", "llm_adapter_unconnected"] = "mock"
    generator_model: str
    prompt_id: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    seed: int


class PipelineBatchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_count: int
    valid_count: int
    invalid_count: int
    duplicate_count: int
    evaluated_count: int
    rejected_count: int
    accepted_count: int
    n_experiments: int
    family_trial_counts: dict[str, int] = Field(default_factory=dict)
    research_eligibility: str
    eligibility_blockers: list[str] = Field(default_factory=list)
    invalid_errors: list[dict[str, Any]] = Field(default_factory=list)
    specs: list[StrategySpec] = Field(default_factory=list)
    experiment_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

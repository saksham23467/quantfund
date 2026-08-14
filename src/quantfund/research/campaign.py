"""Immutable ResearchCampaignConfig + deterministic hashing."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from quantfund.data.ingest.checksums import hash_json
from quantfund.research.screening import ScreeningPolicy
from quantfund.research.splits import SplitConfig
from quantfund.research.walkforward import WalkForwardConfig


class CampaignPurpose(str, Enum):
    EXPLORATORY_DEVELOPMENT = "exploratory_development"
    RESEARCH = "research"


class ValidationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str = "validation_policy_v1"
    require_finite_sharpe: bool = True
    min_trades: int = 1
    min_validation_sharpe: float | None = None


class RobustnessPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str = "robustness_policy_v1"
    min_pass_rate: float = 0.5
    reject_if_fragile: bool = True


class WalkForwardAcceptancePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str = "walkforward_acceptance_v1"
    min_fraction_positive_windows: float = 0.4
    min_median_window_sharpe: float | None = None


class AcceptancePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str = "acceptance_policy_v1"
    require_research_eligible_dataset: bool = True
    require_sealed_test: bool = True
    max_test_evaluations_per_candidate: int = 1
    walkforward: WalkForwardAcceptancePolicy = Field(
        default_factory=WalkForwardAcceptancePolicy
    )
    robustness: RobustnessPolicy = Field(default_factory=RobustnessPolicy)
    validation: ValidationPolicy = Field(default_factory=ValidationPolicy)


class ResearchCampaignConfig(BaseModel):
    """Frozen campaign configuration. Hash excludes campaign_id / created_at."""

    model_config = ConfigDict(frozen=True)

    campaign_id: str = Field(default_factory=lambda: uuid4().hex)
    campaign_version: str = "v1"
    purpose: CampaignPurpose = CampaignPurpose.EXPLORATORY_DEVELOPMENT
    dataset_id: str
    dataset_version: str
    universe_id: str
    universe_version: str
    calendar_id: str = "NSE_EQ"
    calendar_version: str = "nse_eq_v2023_2025_r1"
    feature_set_id: str = "default_feature_set_v1"
    feature_versions: dict[str, str] = Field(default_factory=dict)
    feature_requests: list[dict[str, Any]] = Field(default_factory=list)
    family_id: str = "default_campaign_family"
    candidate_generator: str = "mock"  # human | mock | llm_adapter
    candidate_budget: int = 20
    experiment_budget: int = 40
    screening_policy: ScreeningPolicy = Field(default_factory=lambda: ScreeningPolicy())
    validation_policy: ValidationPolicy = Field(default_factory=ValidationPolicy)
    robustness_policy: RobustnessPolicy = Field(default_factory=RobustnessPolicy)
    acceptance_policy: AcceptancePolicy = Field(default_factory=AcceptancePolicy)
    walkforward_config: WalkForwardConfig | None = None
    walkforward_enabled: bool = False
    split_config: SplitConfig
    score_policy_version: str = "score_policy_v1"
    cost_model: str = "equity_delivery_v1"
    slippage_model: str = "fixed_bps_5"
    initial_capital: float = 100_000.0
    selection_criterion: str = "validation_sharpe"
    random_seed: int = 42
    code_version: str = "0.6.0"
    symbol: str = "TEST"
    certified_eligibility: str = "development_only"
    source_grade: str = "synthetic"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def canonical_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data.pop("campaign_id", None)
        data.pop("created_at", None)
        return data

    def compute_hash(self) -> str:
        return hash_json(self.canonical_dict())

    def assert_score_policy_v1(self) -> None:
        if self.score_policy_version != "score_policy_v1":
            raise ValueError(
                f"Phase 6 allows only score_policy_v1; got {self.score_policy_version}"
            )

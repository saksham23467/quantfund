"""Immutable experiment configuration and results with deterministic hashing."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from quantfund.data.ingest.checksums import hash_json
from quantfund.research.splits import SplitConfig
from quantfund.research.walkforward import WalkForwardConfig


def config_hash(payload: dict[str, Any]) -> str:
    """Canonical hash of an experiment configuration."""
    return hash_json(payload)


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment_id: str = Field(default_factory=lambda: uuid4().hex)
    strategy_id: str
    strategy_version: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    dataset_id: str
    dataset_version: str
    universe_id: str
    universe_version: str
    feature_versions: dict[str, str] = Field(default_factory=dict)
    feature_requests: list[dict[str, Any]] = Field(default_factory=list)
    cost_model: str
    slippage_model: str
    calendar_id: str
    calendar_version: str
    split_config: SplitConfig | None = None
    walkforward_config: WalkForwardConfig | None = None
    start_date: str
    end_date: str
    initial_capital: float
    random_seed: int = 0
    code_version: str = "0.2.0"
    research_eligibility: str
    # Visible provenance: DEVELOPMENT_DATA must never be mistaken for research.
    data_class: str = ""
    purpose: str = "candidate"  # baseline | candidate | robustness | walkforward_window
    parent_experiment_id: str | None = None
    selection_criterion: str = "validation_sharpe"
    sealed_evaluation: bool = False
    score_policy: str = "score_policy_v1"
    family_id: str = "default_family"

    def canonical_dict(self) -> dict[str, Any]:
        """Stable dict for hashing (excludes experiment_id wall-clock identity)."""
        data = self.model_dump(mode="json")
        # Hash identity of the scientific config, not the UUID label
        data.pop("experiment_id", None)
        return data

    def compute_hash(self) -> str:
        return config_hash(self.canonical_dict())


class ExperimentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment_id: str
    config_hash: str
    status: str  # completed | rejected | failed | exploratory_only
    rejection_reasons: list[str] = Field(default_factory=list)
    metrics_by_split: dict[str, dict[str, Any]] = Field(default_factory=dict)
    robustness_summary: dict[str, Any] | None = None
    score: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    n_trials_in_family: int = 0
    deflated_sharpe: float | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    artifacts_path: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

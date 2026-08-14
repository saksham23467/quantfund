"""Immutable strategy activation for Phase 19 paper — no self-modification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from quantfund.phase15.freeze import (
    FrozenSessionConfig,
    assert_freeze_unchanged,
    freeze_session_config,
)
from quantfund.phase19.selection import PaperCandidate
from quantfund.strategies.spec.models import StrategySpec


@dataclass(frozen=True)
class Phase19ActivationRecord:
    activation_id: str
    mode: str
    candidate_id: str
    strategy_family: str
    strategy_hash: str
    parameter_hash: str
    strategy_spec_hash: str
    dataset_research_hash: str
    code_version: str
    freeze_token: str
    research_accepted: bool
    activated_at: str
    auto_graduate_to_live: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "activation_id": self.activation_id,
            "mode": self.mode,
            "candidate_id": self.candidate_id,
            "strategy_family": self.strategy_family,
            "strategy_hash": self.strategy_hash,
            "parameter_hash": self.parameter_hash,
            "strategy_spec_hash": self.strategy_spec_hash,
            "dataset_research_hash": self.dataset_research_hash,
            "code_version": self.code_version,
            "freeze_token": self.freeze_token,
            "research_accepted": self.research_accepted,
            "activated_at": self.activated_at,
            "auto_graduate_to_live": False,
        }


def build_activation(
    *,
    candidate: PaperCandidate,
    mode: str,
    strategy_spec: StrategySpec | dict[str, Any] | None,
    dataset_research_hash: str,
    code_version: str = "0.2.0",
    risk_config: dict[str, Any] | None = None,
    session_config_hash: str = "",
) -> tuple[Phase19ActivationRecord, FrozenSessionConfig]:
    spec_dict: dict[str, Any]
    if isinstance(strategy_spec, StrategySpec):
        spec_dict = strategy_spec.model_dump(mode="json")
    else:
        spec_dict = dict(strategy_spec or {})

    frozen = freeze_session_config(
        strategy_id=candidate.strategy_family,
        strategy_version="1.0.0",
        strategy_params=dict(candidate.parameters),
        strategy_spec=spec_dict,
        risk_config=risk_config or {},
        execution_model="paper_next_bar_open",
        campaign_id="phase19",
        dataset_provenance=dataset_research_hash,
        session_config_hash=session_config_hash,
    )
    if mode == "PRODUCTION_PAPER_ELIGIBLE" and not candidate.research_accepted:
        raise RuntimeError("activation_requires_research_acceptance")

    act = Phase19ActivationRecord(
        activation_id=f"p19act_{frozen.freeze_token[:16]}",
        mode=mode,
        candidate_id=candidate.candidate_id,
        strategy_family=candidate.strategy_family,
        strategy_hash=frozen.strategy_hash,
        parameter_hash=frozen.parameters_hash,
        strategy_spec_hash=frozen.strategy_spec_hash,
        dataset_research_hash=dataset_research_hash,
        code_version=code_version,
        freeze_token=frozen.freeze_token,
        research_accepted=candidate.research_accepted,
        activated_at=datetime.now(timezone.utc).isoformat(),
        auto_graduate_to_live=False,
    )
    return act, frozen


def assert_strategy_immutable(
    frozen: FrozenSessionConfig,
    *,
    candidate: PaperCandidate,
    strategy_spec: StrategySpec | dict[str, Any] | None,
    risk_config: dict[str, Any] | None = None,
    dataset_research_hash: str = "",
    session_config_hash: str = "",
) -> None:
    spec_dict: dict[str, Any]
    if isinstance(strategy_spec, StrategySpec):
        spec_dict = strategy_spec.model_dump(mode="json")
    else:
        spec_dict = dict(strategy_spec or {})
    current = freeze_session_config(
        strategy_id=candidate.strategy_family,
        strategy_version="1.0.0",
        strategy_params=dict(candidate.parameters),
        strategy_spec=spec_dict,
        risk_config=risk_config or {},
        execution_model="paper_next_bar_open",
        campaign_id="phase19",
        dataset_provenance=dataset_research_hash or frozen.dataset_provenance,
        session_config_hash=session_config_hash or frozen.session_config_hash,
    )
    assert_freeze_unchanged(frozen, current)

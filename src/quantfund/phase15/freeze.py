"""Strategy / config freeze at shadow session start."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from quantfund.paper.models import state_hash


@dataclass(frozen=True)
class FrozenSessionConfig:
    strategy_id: str
    strategy_version: str
    strategy_hash: str
    strategy_spec_hash: str
    feature_versions_hash: str
    parameters_hash: str
    risk_config_hash: str
    execution_model: str
    campaign_id: str
    dataset_provenance: str
    session_config_hash: str
    freeze_token: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_hash": self.strategy_hash,
            "strategy_spec_hash": self.strategy_spec_hash,
            "feature_versions_hash": self.feature_versions_hash,
            "parameters_hash": self.parameters_hash,
            "risk_config_hash": self.risk_config_hash,
            "execution_model": self.execution_model,
            "campaign_id": self.campaign_id,
            "dataset_provenance": self.dataset_provenance,
            "session_config_hash": self.session_config_hash,
            "freeze_token": self.freeze_token,
        }


def _h(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def freeze_session_config(
    *,
    strategy_id: str,
    strategy_version: str,
    strategy_params: dict[str, Any] | None = None,
    strategy_spec: dict[str, Any] | None = None,
    feature_versions: dict[str, str] | None = None,
    risk_config: dict[str, Any] | None = None,
    execution_model: str = "shadow_would_order",
    campaign_id: str = "phase15",
    dataset_provenance: str = "yfinance_simulation",
    session_config_hash: str = "",
) -> FrozenSessionConfig:
    strategy_hash = _h(
        {
            "id": strategy_id,
            "version": strategy_version,
            "params": strategy_params or {},
        }
    )
    return FrozenSessionConfig(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        strategy_hash=strategy_hash,
        strategy_spec_hash=_h(strategy_spec or {"kind": "python_strategy"}),
        feature_versions_hash=_h(feature_versions or {"sma": "v1", "momentum": "v1"}),
        parameters_hash=_h(strategy_params or {}),
        risk_config_hash=_h(risk_config or {}),
        execution_model=execution_model,
        campaign_id=campaign_id,
        dataset_provenance=dataset_provenance,
        session_config_hash=session_config_hash,
        freeze_token=state_hash(
            {
                "strategy_hash": strategy_hash,
                "campaign_id": campaign_id,
                "session_config_hash": session_config_hash,
            }
        ),
    )


def assert_freeze_unchanged(
    frozen: FrozenSessionConfig, current: FrozenSessionConfig
) -> None:
    if frozen.freeze_token != current.freeze_token:
        raise RuntimeError("SESSION_INVALIDATED")
    if frozen.to_dict() != current.to_dict():
        raise RuntimeError("SESSION_INVALIDATED")

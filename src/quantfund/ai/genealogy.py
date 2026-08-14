"""Immutable strategy genealogy + canonical hashing."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from quantfund.strategies.spec.models import StrategySpec

MutationType = Literal["initial", "parameter_change", "feature_change", "rule_change"]


class StrategyGenealogy(BaseModel):
    model_config = ConfigDict(frozen=True)

    family_id: str
    strategy_id: str
    parent_strategy_id: str | None = None
    generation_number: int = 0
    mutation_type: MutationType = "initial"
    generator_type: str = "mock"
    generator_model: str = "mock_v1"
    prompt_id: str = "mock_prompt_v1"
    campaign_id: str | None = None
    candidate_id: str | None = None


def canonical_strategy_payload(spec: StrategySpec) -> dict[str, Any]:
    """Stable payload for hashing (excludes wall-clock / identity noise)."""
    data = spec.model_dump(mode="json", by_alias=True)
    data.pop("strategy_id", None)
    meta = dict(data.get("metadata") or {})
    for key in (
        "created_at",
        "canonical_hash",
        "generator_prompt_id",
        "complexity",
    ):
        meta.pop(key, None)
    data["metadata"] = meta
    return data


def canonical_strategy_hash(spec: StrategySpec) -> str:
    payload = canonical_strategy_payload(spec)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def attach_genealogy(
    spec: StrategySpec,
    genealogy: StrategyGenealogy,
    *,
    complexity: dict[str, Any] | None = None,
) -> StrategySpec:
    meta = dict(spec.metadata)
    meta.update(
        {
            "author": "ai",
            "family_id": genealogy.family_id,
            "parent_strategy_id": genealogy.parent_strategy_id,
            "generation_number": genealogy.generation_number,
            "mutation_type": genealogy.mutation_type,
            "generator_type": genealogy.generator_type,
            "generator_model": genealogy.generator_model,
            "generator_prompt_id": genealogy.prompt_id,
        }
    )
    if genealogy.campaign_id is not None:
        meta["campaign_id"] = genealogy.campaign_id
    if genealogy.candidate_id is not None:
        meta["candidate_id"] = genealogy.candidate_id
    if complexity is not None:
        meta["complexity"] = complexity
    updated = spec.model_copy(
        update={
            "strategy_id": genealogy.strategy_id,
            "metadata": meta,
        }
    )
    meta2 = dict(updated.metadata)
    meta2["canonical_hash"] = canonical_strategy_hash(updated)
    return updated.model_copy(update={"metadata": meta2})

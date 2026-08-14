"""Campaign candidate pool — validate, hash, dedupe, genealogy, budgets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from quantfund.ai.genealogy import StrategyGenealogy, attach_genealogy, canonical_strategy_hash
from quantfund.research.campaign_state import CandidateState, transition_candidate
from quantfund.research.search_space import BudgetExceededError, CampaignBudgets
from quantfund.strategies.spec.models import StrategySpec
from quantfund.strategies.spec.validator import StrategySpecValidator


@dataclass
class CandidateRecord:
    candidate_id: str
    campaign_id: str
    spec: StrategySpec | None
    strategy_hash: str | None
    state: CandidateState
    genealogy: dict[str, Any]
    is_duplicate: bool = False
    duplicate_of: str | None = None
    rejection_reason: str | None = None
    screening: dict[str, Any] | None = None
    validation_experiment_id: str | None = None
    test_experiment_id: str | None = None
    test_evaluations: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    parent_candidate_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "campaign_id": self.campaign_id,
            "strategy_hash": self.strategy_hash,
            "state": self.state.value,
            "genealogy": self.genealogy,
            "is_duplicate": self.is_duplicate,
            "duplicate_of": self.duplicate_of,
            "rejection_reason": self.rejection_reason,
            "screening": self.screening,
            "validation_experiment_id": self.validation_experiment_id,
            "test_experiment_id": self.test_experiment_id,
            "test_evaluations": self.test_evaluations,
            "metrics": self.metrics,
            "created_at": self.created_at,
            "parent_candidate_id": self.parent_candidate_id,
            "spec": self.spec.model_dump(mode="json") if self.spec else None,
        }


@dataclass
class PoolStats:
    generated_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    duplicate_count: int = 0
    screened_count: int = 0
    screen_passed_count: int = 0
    evaluated_count: int = 0
    rejected_count: int = 0
    accepted_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "generated_count": self.generated_count,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "duplicate_count": self.duplicate_count,
            "screened_count": self.screened_count,
            "screen_passed_count": self.screen_passed_count,
            "evaluated_count": self.evaluated_count,
            "rejected_count": self.rejected_count,
            "accepted_count": self.accepted_count,
        }


class CandidatePool:
    """In-memory pool with persistent-friendly serialization."""

    def __init__(
        self,
        *,
        campaign_id: str,
        budgets: CampaignBudgets,
        validator: StrategySpecValidator | None = None,
    ) -> None:
        self.campaign_id = campaign_id
        self.budgets = budgets
        self.validator = validator or StrategySpecValidator()
        self.candidates: list[CandidateRecord] = []
        self._hash_index: dict[str, str] = {}
        self.stats = PoolStats()

    def admit_generated(
        self,
        specs: list[StrategySpec],
        *,
        family_id: str,
        generator_type: str = "mock",
    ) -> list[CandidateRecord]:
        admitted: list[CandidateRecord] = []
        for spec in specs:
            self.stats.generated_count += 1
            try:
                self.budgets.consume_candidate(label=getattr(spec, "name", "cand"))
            except BudgetExceededError:
                # Stop admitting further candidates; record overflow attempt via stats
                break

            candidate_id = uuid4().hex
            result = self.validator.validate(spec)
            if not result.valid:
                self.stats.invalid_count += 1
                self.stats.rejected_count += 1
                rec = CandidateRecord(
                    candidate_id=candidate_id,
                    campaign_id=self.campaign_id,
                    spec=None,
                    strategy_hash=None,
                    state=CandidateState.REJECTED,
                    genealogy={"generator_type": generator_type, "family_id": family_id},
                    rejection_reason="structurally_invalid:"
                    + ",".join(e.code for e in result.errors),
                )
                self.candidates.append(rec)
                admitted.append(rec)
                continue

            # Attach campaign genealogy
            sid = spec.strategy_id or f"cand_{candidate_id[:8]}"
            gene = StrategyGenealogy(
                family_id=family_id,
                strategy_id=sid,
                generator_type=generator_type,
                campaign_id=self.campaign_id,
                candidate_id=candidate_id,
            )
            tagged = attach_genealogy(spec, gene)
            h = canonical_strategy_hash(tagged)

            self.stats.valid_count += 1
            rec = CandidateRecord(
                candidate_id=candidate_id,
                campaign_id=self.campaign_id,
                spec=tagged,
                strategy_hash=h,
                state=CandidateState.GENERATED,
                genealogy={
                    "family_id": family_id,
                    "strategy_id": sid,
                    "generator_type": generator_type,
                    "campaign_id": self.campaign_id,
                    "candidate_id": candidate_id,
                    "parent_candidate_id": None,
                },
            )
            rec.state = transition_candidate(rec.state, CandidateState.VALIDATED)

            if h in self._hash_index:
                self.stats.duplicate_count += 1
                rec.is_duplicate = True
                rec.duplicate_of = self._hash_index[h]
                rec.state = transition_candidate(rec.state, CandidateState.DEDUPLICATED)
                rec.rejection_reason = f"duplicate_of:{rec.duplicate_of}"
                # Duplicates do not proceed; mark rejected for funnel accounting
                rec.state = transition_candidate(rec.state, CandidateState.REJECTED)
                self.stats.rejected_count += 1
            else:
                self._hash_index[h] = candidate_id
                rec.state = transition_candidate(rec.state, CandidateState.DEDUPLICATED)

            self.candidates.append(rec)
            admitted.append(rec)
        return admitted

    def unique_active(self) -> list[CandidateRecord]:
        return [
            c
            for c in self.candidates
            if not c.is_duplicate
            and c.state
            not in {CandidateState.REJECTED, CandidateState.ACCEPTED}
            and c.spec is not None
        ]

    def by_state(self, state: CandidateState) -> list[CandidateRecord]:
        return [c for c in self.candidates if c.state == state]

    def get(self, candidate_id: str) -> CandidateRecord | None:
        for c in self.candidates:
            if c.candidate_id == candidate_id:
                return c
        return None

    def reject(self, candidate: CandidateRecord, reason: str) -> None:
        if candidate.state == CandidateState.REJECTED:
            return
        # Allow reject from any non-terminal via stepwise or direct if allowed
        if candidate.state != CandidateState.REJECTED:
            try:
                candidate.state = transition_candidate(
                    candidate.state, CandidateState.REJECTED
                )
            except Exception:
                # If not directly allowed, force only when already terminal-bound
                # Walk common path: most states can go to REJECTED per FSM
                raise
        candidate.rejection_reason = reason
        self.stats.rejected_count += 1

    def to_serializable(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "stats": self.stats.to_dict(),
            "budgets": self.budgets.snapshot(),
            "hash_index": dict(self._hash_index),
            "candidates": [c.to_dict() for c in self.candidates],
        }

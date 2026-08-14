"""Campaign TEST seal — freeze selection and allow one-shot TEST only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from quantfund.research.campaign_state import CampaignState, CandidateState
from quantfund.research.splits import ChronologicalSplit, SealedTestSetError, SplitConfig


class SealViolationError(PermissionError):
    """Contamination or illegal TEST access."""


# Back-compat aliases
CampaignTestSealError = SealViolationError
TestSealError = SealViolationError


@dataclass
class CampaignTestSeal:
    """Guards sealed TEST evaluation at campaign level."""

    campaign_id: str
    config_hash: str
    selection_criterion: str
    score_policy_version: str
    dataset_id: str
    dataset_version: str
    acceptance_policy_id: str
    sealed: bool = False
    sealed_at: str | None = None
    frozen_candidate_ids: list[str] = field(default_factory=list)
    trial_counters_frozen: dict[str, int] = field(default_factory=dict)
    contamination_events: list[dict[str, Any]] = field(default_factory=list)
    test_evaluation_log: list[str] = field(default_factory=list)

    def seal(
        self,
        *,
        campaign_state: CampaignState,
        candidate_ids: list[str],
        trial_counters: dict[str, int],
        selection_criterion: str,
        config_hash: str,
    ) -> None:
        if campaign_state not in {CampaignState.SEALING, CampaignState.RUNNING}:
            raise SealViolationError(
                f"Cannot seal from campaign state {campaign_state.value}"
            )
        if self.sealed:
            raise SealViolationError("Campaign already sealed")
        if selection_criterion != self.selection_criterion:
            raise SealViolationError("selection_criterion mismatch at seal")
        if config_hash != self.config_hash:
            raise SealViolationError("config_hash mismatch at seal")
        self.frozen_candidate_ids = list(candidate_ids)
        self.trial_counters_frozen = dict(trial_counters)
        self.sealed = True
        self.sealed_at = datetime.now(timezone.utc).isoformat()

    def assert_not_contaminated(self) -> None:
        if self.contamination_events:
            raise SealViolationError(
                f"Campaign contaminated: {self.contamination_events[-1]}"
            )

    def record_contamination(self, code: str, detail: str) -> None:
        self.contamination_events.append(
            {
                "code": code,
                "detail": detail,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def assert_can_add_candidates(self) -> None:
        if self.sealed:
            self.record_contamination(
                "add_after_seal", "attempted to add candidates after seal"
            )
            raise SealViolationError("Cannot add candidates after seal")

    def assert_can_change_selection_criterion(self, new_value: str) -> None:
        if self.sealed and new_value != self.selection_criterion:
            self.record_contamination(
                "selection_criterion_change",
                f"attempted change to {new_value}",
            )
            raise SealViolationError("selection_criterion frozen after seal")

    def assert_can_change_config(self, new_hash: str) -> None:
        if self.sealed and new_hash != self.config_hash:
            self.record_contamination(
                "config_change", f"attempted config hash {new_hash}"
            )
            raise SealViolationError("campaign config frozen after seal")

    def authorize_test_evaluation(
        self,
        *,
        candidate_id: str,
        candidate_state: CandidateState,
        prior_test_evaluations: int,
    ) -> None:
        self.assert_not_contaminated()
        if not self.sealed:
            self.record_contamination(
                "test_before_seal", f"candidate={candidate_id}"
            )
            raise SealViolationError("TEST evaluation before campaign seal")
        if candidate_id not in self.frozen_candidate_ids:
            self.record_contamination(
                "test_unknown_candidate", f"candidate={candidate_id}"
            )
            raise SealViolationError("Candidate not in sealed set")
        if candidate_state != CandidateState.SEALED:
            self.record_contamination(
                "test_bad_state",
                f"candidate={candidate_id} state={candidate_state.value}",
            )
            raise SealViolationError(
                f"Candidate must be SEALED for TEST; got {candidate_state.value}"
            )
        if prior_test_evaluations >= 1:
            self.record_contamination(
                "second_test", f"candidate={candidate_id}"
            )
            raise SealViolationError("Second TEST evaluation forbidden")
        self.test_evaluation_log.append(candidate_id)

    def unlock_split_for_test(
        self, split: ChronologicalSplit, *, sealed_evaluation: bool
    ) -> list:
        if not self.sealed:
            raise SealViolationError("Cannot unlock TEST before seal")
        if not sealed_evaluation:
            raise SealedTestSetError("sealed_evaluation flag required")
        split.unlock_test(sealed_evaluation=True)
        return split.get_test_bars()

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "config_hash": self.config_hash,
            "selection_criterion": self.selection_criterion,
            "score_policy_version": self.score_policy_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "acceptance_policy_id": self.acceptance_policy_id,
            "sealed": self.sealed,
            "sealed_at": self.sealed_at,
            "frozen_candidate_ids": list(self.frozen_candidate_ids),
            "trial_counters_frozen": dict(self.trial_counters_frozen),
            "contamination_events": list(self.contamination_events),
            "test_evaluation_log": list(self.test_evaluation_log),
        }


def assert_test_inaccessible(split: ChronologicalSplit) -> None:
    try:
        split.get_test_bars()
    except SealedTestSetError:
        return
    raise SealViolationError("TEST bars accessible while seal inactive")

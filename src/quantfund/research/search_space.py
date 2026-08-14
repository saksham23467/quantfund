"""Explicit campaign budgets — monotonic, no reset, fail closed on overflow."""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExceededError(ValueError):
    """Raised when a campaign budget would be exceeded."""


@dataclass
class CampaignBudgets:
    """Hard enforcement of candidate / experiment budgets."""

    max_candidates: int
    max_experiments: int
    candidates_consumed: int = 0
    experiments_consumed: int = 0
    _history: list[str] = field(default_factory=list)

    def consume_candidate(self, *, label: str = "candidate") -> None:
        if self.candidates_consumed >= self.max_candidates:
            raise BudgetExceededError(
                f"candidate_budget exhausted "
                f"({self.candidates_consumed}/{self.max_candidates})"
            )
        self.candidates_consumed += 1
        self._history.append(f"candidate:{label}")

    def consume_experiment(self, *, label: str = "experiment") -> None:
        if self.experiments_consumed >= self.max_experiments:
            raise BudgetExceededError(
                f"experiment_budget exhausted "
                f"({self.experiments_consumed}/{self.max_experiments})"
            )
        self.experiments_consumed += 1
        self._history.append(f"experiment:{label}")

    def snapshot(self) -> dict[str, int]:
        return {
            "max_candidates": self.max_candidates,
            "max_experiments": self.max_experiments,
            "candidates_consumed": self.candidates_consumed,
            "experiments_consumed": self.experiments_consumed,
        }

    def restore(self, *, candidates_consumed: int, experiments_consumed: int) -> None:
        """Resume counters — never decreases."""
        if candidates_consumed < self.candidates_consumed:
            raise ValueError("cannot decrease candidates_consumed on resume")
        if experiments_consumed < self.experiments_consumed:
            raise ValueError("cannot decrease experiments_consumed on resume")
        if candidates_consumed > self.max_candidates:
            raise BudgetExceededError("restored candidates exceed budget")
        if experiments_consumed > self.max_experiments:
            raise BudgetExceededError("restored experiments exceed budget")
        self.candidates_consumed = candidates_consumed
        self.experiments_consumed = experiments_consumed

"""Experiment record schema for Phase 19 controlled strategy research.

Captures every mandated field for a single candidate experiment, including full
data/universe provenance, the three period splits, the explicit cost/slippage
models, the performance metrics per split, DSR, and the trial count used for the
deflated-Sharpe accounting. Records are pure data — they never trade.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SplitMetrics:
    """Performance metrics for one period split (train / validation / test)."""

    n_obs: int
    n_trades: int
    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    turnover: float
    exposure: float
    win_rate: float
    profit_factor: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Period:
    start: str
    end: str

    def to_dict(self) -> dict[str, str]:
        return {"start": self.start, "end": self.end}


@dataclass(frozen=True)
class CostModel:
    model_id: str
    transaction_cost_bps: float
    slippage_bps: float
    execution_timing: str  # e.g. "next_open_raw" — realistic, no look-ahead

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyExperimentRecord:
    """A single immutable-by-convention experiment record."""

    experiment_id: str
    family: str
    strategy_id: str
    parameters: dict[str, Any]

    # Data + universe provenance
    dataset_id: str
    dataset_version: str
    dataset_hash: str
    universe_id: str
    universe_version: str

    # Periods
    train_period: Period
    validation_period: Period
    test_period: Period

    # Execution assumptions (explicitly modeled)
    cost_model: CostModel

    # Metrics per split
    metrics_by_split: dict[str, SplitMetrics] = field(default_factory=dict)

    # Multiple-testing accounting
    deflated_sharpe: float | None = None
    trial_count: int = 0

    # Funnel outcome
    stage_reached: str = "created"  # created|data_integrity|validation|oos|robustness|dsr|accepted
    rejected: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    passed_validation: bool = False
    passed_oos: bool = False
    passed_robustness: bool = False
    passed_dsr: bool = False
    accepted: bool = False
    promoted: bool = False  # ALWAYS False here — no auto-promotion
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "family": self.family,
            "strategy_id": self.strategy_id,
            "parameters": dict(self.parameters),
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_hash": self.dataset_hash,
            "universe_id": self.universe_id,
            "universe_version": self.universe_version,
            "train_period": self.train_period.to_dict(),
            "validation_period": self.validation_period.to_dict(),
            "test_period": self.test_period.to_dict(),
            "cost_model": self.cost_model.to_dict(),
            "metrics_by_split": {
                k: v.to_dict() for k, v in self.metrics_by_split.items()
            },
            "deflated_sharpe": self.deflated_sharpe,
            "trial_count": self.trial_count,
            "stage_reached": self.stage_reached,
            "rejected": self.rejected,
            "rejection_reasons": list(self.rejection_reasons),
            "passed_validation": self.passed_validation,
            "passed_oos": self.passed_oos,
            "passed_robustness": self.passed_robustness,
            "passed_dsr": self.passed_dsr,
            "accepted": self.accepted,
            "promoted": self.promoted,
            "notes": list(self.notes),
        }

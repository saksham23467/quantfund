"""Controlled Phase 19 strategy-research orchestrator.

Enforces, in order:
1. Research-eligibility PREREQUISITE (fails closed → no search runs).
2. A fixed research budget (candidate + experiment caps, monotonic).
3. Per-candidate data-integrity gate (PIT universe, exchange-grade data, RAW
   prices, explicit costs + slippage, realistic timing, no look-ahead, no
   survivorship).
4. Validation → OOS → robustness → DSR funnel, preserving the existing DSR
   trial accounting (``deflated_sharpe_ratio``).

It NEVER auto-promotes the best strategy, NEVER enables paper/live trading, and
NEVER submits broker orders. If zero candidates pass, that is a valid result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from quantfund.research.multiple_testing import deflated_sharpe_ratio
from quantfund.research.search_space import BudgetExceededError, CampaignBudgets
from quantfund.research.strategy_research.families import (
    CandidateSpec,
    StrategyFamily,
    enumerate_candidates,
)
from quantfund.research.strategy_research.gates import (
    DataIntegrityRequirements,
    GatePolicy,
    PrerequisiteResult,
    dsr_gate,
    evaluate_prerequisite,
    oos_gate,
    robustness_gate,
    validation_gate,
)
from quantfund.research.strategy_research.record import (
    CostModel,
    Period,
    SplitMetrics,
    StrategyExperimentRecord,
)


@dataclass(frozen=True)
class ResearchContext:
    """Shared, authoritative provenance for the whole search."""

    dataset_id: str
    dataset_version: str
    dataset_hash: str
    universe_id: str
    universe_version: str
    train_period: Period
    validation_period: Period
    test_period: Period
    cost_model: CostModel


@dataclass(frozen=True)
class EvaluationOutput:
    """Evaluator output for one candidate. Never produced for ineligible data."""

    data_integrity: DataIntegrityRequirements
    metrics_by_split: dict[str, SplitMetrics] = field(default_factory=dict)
    robustness_pass_rate: float | None = None
    robustness_fragile: bool = True
    oos_n_obs: int = 0


class CandidateEvaluator(Protocol):
    """Runs a PIT, RAW-price, cost+slippage-aware backtest for one candidate.

    Implementations MUST fail closed (return unsatisfied data-integrity) rather
    than fabricate metrics when the required data guarantees are unavailable.
    """

    def evaluate(
        self, spec: CandidateSpec, context: ResearchContext
    ) -> EvaluationOutput: ...


class FailClosedEvaluator:
    """Default evaluator: refuses every candidate on data-integrity grounds.

    Used when no research-eligible, exchange-grade, PIT-safe evaluator exists.
    It never invents metrics.
    """

    def evaluate(
        self, spec: CandidateSpec, context: ResearchContext
    ) -> EvaluationOutput:
        return EvaluationOutput(
            data_integrity=DataIntegrityRequirements(
                point_in_time_universe=False,
                exchange_grade_data=False,
                raw_execution_prices=False,
                transaction_costs_modeled=False,
                slippage_modeled=False,
                realistic_execution_timing=False,
                no_look_ahead=False,
                no_survivorship_bias=False,
            )
        )


@dataclass
class StrategyResearchResult:
    prerequisite: PrerequisiteResult
    ran_search: bool
    stopped_reason: str | None
    budget: dict[str, int]
    gate_policy: dict[str, Any]
    trial_count: int
    records: list[StrategyExperimentRecord] = field(default_factory=list)
    families: list[str] = field(default_factory=list)

    def funnel(self) -> dict[str, int]:
        tested = len(self.records)
        return {
            "candidates_tested": tested,
            "candidates_rejected": sum(1 for r in self.records if r.rejected),
            "candidates_passing_validation": sum(
                1 for r in self.records if r.passed_validation
            ),
            "candidates_passing_oos": sum(1 for r in self.records if r.passed_oos),
            "candidates_passing_robustness": sum(
                1 for r in self.records if r.passed_robustness
            ),
            "candidates_passing_dsr": sum(1 for r in self.records if r.passed_dsr),
            "final_accepted_candidates": sum(1 for r in self.records if r.accepted),
        }

    def accepted_ids(self) -> list[str]:
        return [r.strategy_id for r in self.records if r.accepted]


def _new_record(
    spec: CandidateSpec, context: ResearchContext
) -> StrategyExperimentRecord:
    return StrategyExperimentRecord(
        experiment_id=uuid4().hex,
        family=spec.family.value,
        strategy_id=spec.strategy_id,
        parameters=dict(spec.parameters),
        dataset_id=context.dataset_id,
        dataset_version=context.dataset_version,
        dataset_hash=context.dataset_hash,
        universe_id=context.universe_id,
        universe_version=context.universe_version,
        train_period=context.train_period,
        validation_period=context.validation_period,
        test_period=context.test_period,
        cost_model=context.cost_model,
    )


def run_strategy_research(
    *,
    phase18_payload: dict[str, Any] | None,
    pit_payload: dict[str, Any] | None,
    context: ResearchContext | None = None,
    evaluator: CandidateEvaluator | None = None,
    families: list[StrategyFamily] | None = None,
    max_candidates: int = 40,
    max_experiments: int = 40,
    gate_policy: GatePolicy | None = None,
) -> StrategyResearchResult:
    """Run the controlled strategy search, gated behind research eligibility."""
    prereq = evaluate_prerequisite(
        phase18_payload=phase18_payload, pit_payload=pit_payload
    )
    policy = gate_policy or GatePolicy()
    budgets = CampaignBudgets(
        max_candidates=max_candidates, max_experiments=max_experiments
    )
    fam_values = [f.value for f in (families or list(StrategyFamily))]

    if not prereq.research_eligible:
        # Fail closed: strategy research must not begin. Zero candidates tested.
        return StrategyResearchResult(
            prerequisite=prereq,
            ran_search=False,
            stopped_reason="research_eligibility_false",
            budget=budgets.snapshot(),
            gate_policy=policy.to_dict(),
            trial_count=0,
            records=[],
            families=fam_values,
        )

    if context is None:
        raise ValueError("ResearchContext required once prerequisite is satisfied")
    evaluator = evaluator or FailClosedEvaluator()

    candidates = enumerate_candidates(families)
    records: list[StrategyExperimentRecord] = []

    # Pass 1: data-integrity + evaluation + validation/OOS/robustness gates.
    scored: list[tuple[StrategyExperimentRecord, EvaluationOutput]] = []
    for spec in candidates:
        try:
            budgets.consume_candidate(label=spec.strategy_id)
        except BudgetExceededError:
            break
        record = _new_record(spec, context)
        records.append(record)

        output = evaluator.evaluate(spec, context)
        integrity = output.data_integrity
        if not integrity.satisfied:
            record.stage_reached = "data_integrity"
            record.rejected = True
            record.rejection_reasons.extend(integrity.failures())
            continue

        try:
            budgets.consume_experiment(label=spec.strategy_id)
        except BudgetExceededError:
            record.stage_reached = "data_integrity"
            record.rejected = True
            record.rejection_reasons.append("experiment_budget_exhausted")
            continue

        record.metrics_by_split = dict(output.metrics_by_split)
        val = output.metrics_by_split.get("validation")
        oos = output.metrics_by_split.get("test")
        if val is None or oos is None:
            record.stage_reached = "validation"
            record.rejected = True
            record.rejection_reasons.append("missing_split_metrics")
            continue

        val_reasons = validation_gate(val, policy)
        record.stage_reached = "validation"
        if val_reasons:
            record.rejected = True
            record.rejection_reasons.extend(val_reasons)
            continue
        record.passed_validation = True

        oos_reasons = oos_gate(oos, policy)
        record.stage_reached = "oos"
        if oos_reasons:
            record.rejected = True
            record.rejection_reasons.extend(oos_reasons)
            continue
        record.passed_oos = True

        rob_reasons = robustness_gate(
            output.robustness_pass_rate, output.robustness_fragile, policy
        )
        record.stage_reached = "robustness"
        if rob_reasons:
            record.rejected = True
            record.rejection_reasons.extend(rob_reasons)
            continue
        record.passed_robustness = True

        scored.append((record, output))

    # Trial count for DSR = number of experiments that reached scoring.
    # This preserves honest multiple-testing accounting (no undercount).
    trial_count = budgets.experiments_consumed

    # Pass 2: DSR gate using the full trial count.
    for record, output in scored:
        oos = output.metrics_by_split["test"]
        record.trial_count = trial_count
        dsr = deflated_sharpe_ratio(
            oos.sharpe, n_obs=output.oos_n_obs or oos.n_obs, n_trials=trial_count
        )
        record.deflated_sharpe = dsr
        dsr_reasons = dsr_gate(dsr, policy)
        record.stage_reached = "dsr"
        if dsr_reasons:
            record.rejected = True
            record.rejection_reasons.extend(dsr_reasons)
            continue
        record.passed_dsr = True
        record.accepted = True
        record.stage_reached = "accepted"
        # No auto-promotion — accepted candidates are NOT activated.
        record.promoted = False
        record.notes.append("accepted_research_candidate (NOT promoted, NOT traded)")

    # Any record that never reached scoring keeps trial_count for provenance.
    for record in records:
        if record.trial_count == 0:
            record.trial_count = trial_count

    return StrategyResearchResult(
        prerequisite=prereq,
        ran_search=True,
        stopped_reason=None,
        budget=budgets.snapshot(),
        gate_policy=policy.to_dict(),
        trial_count=trial_count,
        records=records,
        families=fam_values,
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

"""Controlled Phase 19 strategy-research framework.

Strategy research is gated behind research eligibility: it may only run when the
dataset is certified research-eligible AND the PIT universe layer is
research-grade. Every candidate must use a point-in-time universe, exchange-grade
data, RAW execution prices, explicit transaction costs, explicit slippage, and
realistic execution timing, with no look-ahead and no survivorship bias.

The framework preserves the existing DSR trial accounting, uses a fixed research
budget, and NEVER auto-promotes, enables paper/live trading, or submits orders.
"""

from quantfund.research.strategy_research.families import (
    FAMILY_CATALOGUE,
    CandidateSpec,
    FamilySpec,
    StrategyFamily,
    enumerate_candidates,
)
from quantfund.research.strategy_research.framework import (
    CandidateEvaluator,
    EvaluationOutput,
    FailClosedEvaluator,
    ResearchContext,
    StrategyResearchResult,
    run_strategy_research,
)
from quantfund.research.strategy_research.gates import (
    DataIntegrityRequirements,
    GatePolicy,
    PrerequisiteResult,
    evaluate_prerequisite,
)
from quantfund.research.strategy_research.record import (
    CostModel,
    Period,
    SplitMetrics,
    StrategyExperimentRecord,
)
from quantfund.research.strategy_research.runner import (
    run_phase19_strategy_research,
)

__all__ = [
    "FAMILY_CATALOGUE",
    "CandidateEvaluator",
    "CandidateSpec",
    "CostModel",
    "DataIntegrityRequirements",
    "EvaluationOutput",
    "FailClosedEvaluator",
    "FamilySpec",
    "GatePolicy",
    "Period",
    "PrerequisiteResult",
    "ResearchContext",
    "SplitMetrics",
    "StrategyExperimentRecord",
    "StrategyFamily",
    "StrategyResearchResult",
    "enumerate_candidates",
    "evaluate_prerequisite",
    "run_phase19_strategy_research",
    "run_strategy_research",
]

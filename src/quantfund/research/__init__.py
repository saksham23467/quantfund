"""Quantitative research engine (Phase 2). Generation ≠ evaluation."""

from quantfund.research.experiment import ExperimentConfig, ExperimentResult, config_hash
from quantfund.research.splits import ChronologicalSplit, SealedTestSetError, SplitConfig

__all__ = [
    "ExperimentConfig",
    "ExperimentResult",
    "config_hash",
    "SplitConfig",
    "ChronologicalSplit",
    "SealedTestSetError",
]

"""Phase 18 — controlled strategy research / fixed-grammar search."""

from quantfund.phase18.dataset_eligibility import run_phase18_dataset_eligibility
from quantfund.phase18.pipeline import run_phase18_search

__all__ = ["run_phase18_search", "run_phase18_dataset_eligibility"]

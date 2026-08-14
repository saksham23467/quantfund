"""Phase 12 — Controlled paper trading activation (simulation only; live disabled)."""

from quantfund.phase12.activation import (
    PAPER_ACTIVATION_CONFIRM_PHRASE,
    PaperActivationRecord,
    create_paper_activation_record,
    verify_paper_activation_record,
)
from quantfund.phase12.eligibility import (
    ControlledPaperEligibilityDecision,
    ControlledSimulationPaperGate,
)
from quantfund.phase12.engine import ControlledPaperEngine, ControlledPaperResult

__all__ = [
    "PAPER_ACTIVATION_CONFIRM_PHRASE",
    "PaperActivationRecord",
    "create_paper_activation_record",
    "verify_paper_activation_record",
    "ControlledPaperEligibilityDecision",
    "ControlledSimulationPaperGate",
    "ControlledPaperEngine",
    "ControlledPaperResult",
]

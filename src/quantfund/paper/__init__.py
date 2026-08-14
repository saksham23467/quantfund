"""Phase 8 paper-trading kernel (broker-independent, simulated capital only).

Live brokers live under ``quantfund.execution`` (empty in Phase 8).
Strategies must never import execution/fills adapters.
"""

from quantfund.paper.eligibility import PaperEligibilityDecision, PaperEligibilityGate
from quantfund.paper.kill_switch import KillSwitch, KillSwitchState
from quantfund.paper.models import (
    MarketDataEvent,
    PaperSessionConfig,
    SessionMode,
    deterministic_id,
)
from quantfund.paper.orders import (
    BACKTEST_STATUS_MAP,
    InvalidPaperOrderTransition,
    OrderIntent,
    PaperOrderStatus,
)
from quantfund.paper.replay import replay_deterministic, run_paper_session
from quantfund.paper.session import PaperSession, PaperSessionResult

__all__ = [
    "BACKTEST_STATUS_MAP",
    "InvalidPaperOrderTransition",
    "KillSwitch",
    "KillSwitchState",
    "MarketDataEvent",
    "OrderIntent",
    "PaperEligibilityDecision",
    "PaperEligibilityGate",
    "PaperOrderStatus",
    "PaperSession",
    "PaperSessionConfig",
    "PaperSessionResult",
    "SessionMode",
    "deterministic_id",
    "replay_deterministic",
    "run_paper_session",
]

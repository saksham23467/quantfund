"""Real-market-data PAPER trading (NOT live trading).

Architecture:

    Zerodha market data -> market-data adapter -> strategy -> risk engine ->
    PaperExecutionAdapter -> simulated fills -> paper portfolio

Invariants (declared in :mod:`quantfund.paper_realdata.modes`):

    DATA_SOURCE    = ZERODHA
    EXECUTION_MODE = PAPER
    BROKER_WRITES  = DISABLED

No real broker order submission, ``place_order`` unreachable, ``orders_submitted``
stays 0, live trading DISABLED, kill switch ARMED. The eligibility, strategy
acceptance, risk, kill-switch, reconciliation, and stale-data gates are never
bypassed. This package provides a fail-closed PREFLIGHT that stops before the
first paper session.
"""

from quantfund.paper_realdata.broker_guard import (
    RealBrokerWriteError,
    assert_no_real_broker_write_capability,
)
from quantfund.paper_realdata.connectivity import check_zerodha_data_connectivity
from quantfund.paper_realdata.modes import (
    ARCHITECTURE,
    BROKER_WRITES,
    DATA_SOURCE,
    EXECUTION_MODE,
    PaperModeManifest,
)
from quantfund.paper_realdata.preflight import run_realdata_paper_preflight
from quantfund.paper_realdata.strategy_gate import check_strategy_acceptance

__all__ = [
    "ARCHITECTURE",
    "BROKER_WRITES",
    "DATA_SOURCE",
    "EXECUTION_MODE",
    "PaperModeManifest",
    "RealBrokerWriteError",
    "assert_no_real_broker_write_capability",
    "check_strategy_acceptance",
    "check_zerodha_data_connectivity",
    "run_realdata_paper_preflight",
]

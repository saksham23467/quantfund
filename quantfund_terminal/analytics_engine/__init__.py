"""QuantFund Research Terminal — analytics engine.

Pure-Python (numpy/pandas) computation library for performance metrics, factor
research, portfolio analytics and risk. It contains NO trading/execution code
and NEVER places orders. It is used by the read-only research_api to power the
investor-demo panels. Backtests run here are clearly labelled as running on the
selected dataset and inherit that dataset's certification verdict — a
DEVELOPMENT_ONLY dataset produces DEVELOPMENT_ONLY (non-research) results.
"""

from quantfund_terminal.analytics_engine.metrics import (
    PerformanceSummary,
    summarize_returns,
)

__all__ = ["PerformanceSummary", "summarize_returns"]

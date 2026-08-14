"""Resolve ExperimentConfig cost/slippage IDs to concrete models.

Unknown IDs fail closed — no silent defaults.
"""

from __future__ import annotations

import re

from quantfund.backtest.broker_sim import SlippageModel
from quantfund.backtest.costs import CostModel, EquityDeliveryCostModel


class UnknownExecutionModelError(ValueError):
    """Raised when cost_model or slippage_model ID is not registered."""


_FIXED_BPS = re.compile(r"^fixed_bps_(\d+(?:\.\d+)?)$")


def resolve_cost_model(cost_model_id: str) -> CostModel:
    if cost_model_id == "equity_delivery_v1":
        return EquityDeliveryCostModel()
    raise UnknownExecutionModelError(
        f"Unknown cost_model={cost_model_id!r}. "
        "Supported: equity_delivery_v1. No silent fallback."
    )


def resolve_slippage_model(slippage_model_id: str) -> SlippageModel:
    m = _FIXED_BPS.match(slippage_model_id)
    if m:
        return SlippageModel(bps=float(m.group(1)))
    raise UnknownExecutionModelError(
        f"Unknown slippage_model={slippage_model_id!r}. "
        "Supported: fixed_bps_<N> (e.g. fixed_bps_5). No silent fallback."
    )


def resolve_execution_models(
    *,
    cost_model: str,
    slippage_model: str,
) -> tuple[CostModel, SlippageModel]:
    return resolve_cost_model(cost_model), resolve_slippage_model(slippage_model)

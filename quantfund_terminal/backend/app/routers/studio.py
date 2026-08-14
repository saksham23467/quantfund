"""Portfolio Analytics Studio: factor attribution, risk decomposition, scenarios."""

from __future__ import annotations

from fastapi import APIRouter

from quantfund_terminal.analytics_engine.attribution import factor_attribution
from quantfund_terminal.analytics_engine.portfolio import normalize_holdings
from quantfund_terminal.analytics_engine.risk_decomposition import risk_decomposition
from quantfund_terminal.analytics_engine.scenario import scenario_analysis
from quantfund_terminal.backend.app.schemas import ScenarioRequest, StudioRequest
from quantfund_terminal.backend.app.services.panel import get_panel

router = APIRouter(prefix="/api/v2/studio", tags=["studio"])


@router.post("/attribution")
def attribution(req: StudioRequest) -> dict:
    panel = get_panel()
    weights = normalize_holdings([h.model_dump() for h in req.holdings], panel.prices)
    result = factor_attribution(panel.prices, panel.volumes, weights, lookback=req.lookback)
    result["data_class"] = panel.data_class
    return result


@router.post("/risk-decomposition")
def risk_decomp(req: StudioRequest) -> dict:
    panel = get_panel()
    result = risk_decomposition([h.model_dump() for h in req.holdings], panel.prices)
    result["data_class"] = panel.data_class
    return result


@router.post("/scenario")
def scenario(req: ScenarioRequest) -> dict:
    panel = get_panel()
    result = scenario_analysis(
        [h.model_dump() for h in req.holdings],
        panel.prices,
        panel.volumes,
        custom=req.custom,
        lookback=req.lookback,
    )
    result["data_class"] = panel.data_class
    return result

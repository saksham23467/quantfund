"""Risk Command Center endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from quantfund_terminal.analytics_engine.risk import risk_snapshot
from quantfund_terminal.analytics_engine.sample_data import SECTOR_MAP
from quantfund_terminal.backend.app.schemas import RiskRequest
from quantfund_terminal.backend.app.services.panel import get_panel

router = APIRouter(tags=["risk"])


@router.post("/api/risk")
def risk(req: RiskRequest) -> dict:
    panel = get_panel()
    holdings = [h.model_dump() for h in req.holdings]
    result = risk_snapshot(holdings, panel.prices, sector_map=SECTOR_MAP)
    result["data_class"] = panel.data_class
    return result

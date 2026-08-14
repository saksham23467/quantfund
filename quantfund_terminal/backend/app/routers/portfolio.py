"""Portfolio Analytics endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from quantfund_terminal.analytics_engine.portfolio import analyze_portfolio
from quantfund_terminal.analytics_engine.sample_data import SECTOR_MAP
from quantfund_terminal.backend.app.schemas import PortfolioRequest
from quantfund_terminal.backend.app.services.panel import get_panel

router = APIRouter(tags=["portfolio"])


@router.post("/api/portfolio")
def portfolio(req: PortfolioRequest) -> dict:
    panel = get_panel()
    holdings = [h.model_dump() for h in req.holdings]
    result = analyze_portfolio(holdings, panel.prices, sector_map=SECTOR_MAP)
    result["data_class"] = panel.data_class
    return result

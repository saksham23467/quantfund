"""Factor Research endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from quantfund_terminal.analytics_engine.factors import factor_panel_summary
from quantfund_terminal.backend.app.services.panel import get_panel

router = APIRouter(tags=["factors"])


@router.get("/api/factors")
def factors(lookback: int = 126) -> dict:
    panel = get_panel()
    summary = factor_panel_summary(panel.prices, panel.volumes, lookback=lookback)
    summary["data_class"] = panel.data_class
    summary["disclaimer"] = (
        "Synthetic demo factors. value/quality are labelled proxies without "
        "certified fundamentals."
    )
    return summary

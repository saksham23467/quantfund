"""Backtest Engine endpoint (gated, cost/slippage-aware, next-bar execution)."""

from __future__ import annotations

from fastapi import APIRouter

from quantfund_terminal.analytics_engine.backtest import BacktestConfig, run_backtest
from quantfund_terminal.backend.app.schemas import BacktestRequest
from quantfund_terminal.backend.app.services import certification_service
from quantfund_terminal.backend.app.services.panel import get_panel

router = APIRouter(tags=["backtest"])

_FAMILY_MAP = {
    "momentum": "momentum",
    "trend": "trend",
    "trend_following": "trend",
    "mean_reversion": "mean_reversion",
    "breakout": "breakout",
    "volatility": "volatility",
    "volatility_regime": "volatility",
    "low_vol": "volatility",
}


@router.post("/api/backtest")
def backtest(req: BacktestRequest) -> dict:
    panel = get_panel()
    cfg = BacktestConfig(
        family=_FAMILY_MAP.get(req.family, "momentum"),
        lookback=req.lookback,
        holding_top_n=req.holding_top_n,
        rebalance_days=req.rebalance_days,
        cost_bps=req.cost_bps,
        slippage_bps=req.slippage_bps,
        start=req.start,
        end=req.end,
    )
    result = run_backtest(panel.prices, cfg, data_class=panel.data_class)
    cert = certification_service.get_certification()
    payload = result.as_dict()
    payload["certification"] = {
        "verdict": cert.get("verdict"),
        "research_eligible": cert.get("research_eligible", False),
        "banner": (
            "RESULTS ARE ILLUSTRATIVE — dataset is "
            f"{cert.get('verdict', 'DEVELOPMENT_ONLY')}. Not a research-eligible "
            "backtest until a certified dataset is connected."
        ),
    }
    return payload

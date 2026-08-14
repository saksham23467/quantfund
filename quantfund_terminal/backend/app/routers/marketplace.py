"""Strategy Marketplace endpoints (leaderboard + reproducibility proofs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from quantfund_terminal.analytics_engine.backtest import BacktestConfig, run_backtest
from quantfund_terminal.backend.app.auth import TenantContext, require_role
from quantfund_terminal.backend.app.db import get_db
from quantfund_terminal.backend.app.db.models import Backtest, Strategy
from quantfund_terminal.backend.app.schemas import PublishRequest
from quantfund_terminal.backend.app.services import marketplace_service
from quantfund_terminal.backend.app.services.panel import get_panel
from quantfund_terminal.backend.app.services.records_service import append_record, audit
from quantfund_terminal.backend.app.util.hashing import content_hash

router = APIRouter(prefix="/api/v2", tags=["marketplace"])


@router.get("/marketplace")
def marketplace(db: Session = Depends(get_db)) -> dict:
    return marketplace_service.combined_leaderboard(db)


@router.get("/marketplace/{backtest_id}/proof")
def proof(backtest_id: int, db: Session = Depends(get_db)) -> dict:
    result = marketplace_service.reproducibility_proof(db, backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="backtest not found")
    return result


@router.post("/marketplace/publish")
def publish(
    req: PublishRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("pm")),
) -> dict:
    """Run a demo backtest and publish it to the marketplace with a proof.

    Runs on DEMO_SYNTHETIC data → status RESEARCH_ONLY (never ACCEPTED).
    """
    panel = get_panel()
    cfg = BacktestConfig(
        family=req.family,
        lookback=int(req.params.get("lookback", 126)),
        holding_top_n=int(req.params.get("holding_top_n", 5)),
        rebalance_days=int(req.params.get("rebalance_days", 21)),
        cost_bps=req.cost_bps,
        slippage_bps=req.slippage_bps,
    )
    result = run_backtest(panel.prices, cfg, data_class=panel.data_class)
    metrics = result.summary.as_dict()

    strat = Strategy(
        org_id=ctx.org_id,
        name=req.name,
        family=req.family,
        params=req.params,
        status="RESEARCH_ONLY",
        visibility="marketplace",
        created_by=ctx.user_email,
    )
    db.add(strat)
    db.flush()

    dataset_hash = content_hash({"data_class": panel.data_class, "source": panel.source})
    experiment_hash = content_hash({"config": cfg.__dict__, "metrics": metrics})
    bt = Backtest(
        strategy_id=strat.id,
        start=cfg.start,
        end=cfg.end,
        cost_bps=cfg.cost_bps,
        slippage_bps=cfg.slippage_bps,
        metrics=metrics,
        dsr=None,
        data_class=panel.data_class,
        dataset_hash=dataset_hash,
        experiment_hash=experiment_hash,
    )
    db.add(bt)
    db.flush()

    append_record(
        db,
        kind="backtest",
        ref_id=str(bt.id),
        org_id=ctx.org_id,
        payload={"config": cfg.__dict__, "metrics": metrics, "dataset_hash": dataset_hash},
    )
    audit(
        db,
        action="PUBLISH_MARKETPLACE",
        actor=ctx.user_email,
        org_id=ctx.org_id,
        entity_type="backtest",
        entity_id=str(bt.id),
        meta={"family": req.family},
    )
    db.commit()

    return {
        "strategy_id": strat.id,
        "backtest_id": bt.id,
        "status": strat.status,
        "metrics": metrics,
        "proof": {"dataset_hash": dataset_hash, "experiment_hash": experiment_hash},
        "banner": "Published to marketplace as RESEARCH_ONLY (DEMO_SYNTHETIC data).",
    }

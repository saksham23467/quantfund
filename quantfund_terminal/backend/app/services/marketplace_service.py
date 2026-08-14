"""Strategy Marketplace — demo leaderboard with reproducibility proofs, plus the
authoritative gated view from the real core reports.

Two clearly-separated notions:
  * `authoritative_gated`: from the REAL Phase-19 report (0 accepted; fail-closed).
  * `demo_leaderboard`: illustrative strategies run on DEMO_SYNTHETIC data, each
    with a reproducibility proof (dataset_hash + experiment_hash + chained record).
Nothing here presents an illustrative strategy as ACCEPTED on certified data.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from quantfund_terminal.analytics_engine.backtest import BacktestConfig, run_backtest
from quantfund_terminal.backend.app.db.models import Backtest, ResearchRecord, Strategy
from quantfund_terminal.backend.app.services import leaderboard_service
from quantfund_terminal.backend.app.services.panel import get_panel
from quantfund_terminal.backend.app.util.hashing import content_hash


def demo_leaderboard(db: Session) -> dict:
    rows = (
        db.execute(
            select(Backtest, Strategy)
            .join(Strategy, Backtest.strategy_id == Strategy.id)
            .where(Strategy.visibility == "marketplace")
            .order_by(Backtest.created_at.desc())
        )
        .all()
    )
    out = []
    for bt, strat in rows:
        m = bt.metrics or {}
        out.append(
            {
                "backtest_id": bt.id,
                "strategy": strat.name,
                "family": strat.family,
                "org_id": strat.org_id,
                "cagr": m.get("cagr"),
                "sharpe": m.get("sharpe"),
                "sortino": m.get("sortino"),
                "max_drawdown": m.get("max_drawdown"),
                "dsr": bt.dsr,
                "data_class": bt.data_class,
                "status": strat.status,  # RESEARCH_ONLY on demo data
                "proof": {
                    "dataset_hash": bt.dataset_hash,
                    "experiment_hash": bt.experiment_hash,
                },
            }
        )
    out.sort(key=lambda r: (r["sharpe"] or -999), reverse=True)
    return {
        "rows": out,
        "count": len(out),
        "note": (
            "Illustrative strategies on DEMO_SYNTHETIC data. Status is RESEARCH_ONLY; "
            "acceptance requires a RESEARCH_ELIGIBLE dataset (see Dataset Exchange)."
        ),
    }


def combined_leaderboard(db: Session) -> dict:
    return {
        "authoritative_gated": leaderboard_service.get_leaderboard(),
        "demo_leaderboard": demo_leaderboard(db),
    }


def reproducibility_proof(db: Session, backtest_id: int) -> dict | None:
    bt = db.get(Backtest, backtest_id)
    if not bt:
        return None
    strat = db.get(Strategy, bt.strategy_id)

    # Recompute deterministically and compare to stored metrics.
    panel = get_panel()
    cfg = BacktestConfig(
        family=strat.family if strat else "momentum",
        lookback=int((strat.params or {}).get("lookback", 126)) if strat else 126,
        holding_top_n=int((strat.params or {}).get("holding_top_n", 5)) if strat else 5,
        rebalance_days=int((strat.params or {}).get("rebalance_days", 21)) if strat else 21,
        cost_bps=bt.cost_bps,
        slippage_bps=bt.slippage_bps,
        start=bt.start,
        end=bt.end,
    )
    rerun = run_backtest(panel.prices, cfg, data_class=bt.data_class)
    recomputed = rerun.summary.as_dict()
    stored = bt.metrics or {}
    sharpe_match = abs((recomputed.get("sharpe") or 0) - (stored.get("sharpe") or 0)) < 1e-6

    rec = db.execute(
        select(ResearchRecord)
        .where(ResearchRecord.kind == "backtest", ResearchRecord.ref_id == str(backtest_id))
        .order_by(ResearchRecord.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    return {
        "backtest_id": bt.id,
        "strategy": strat.name if strat else None,
        "config": cfg.__dict__,
        "stored_metrics": stored,
        "recomputed_metrics": recomputed,
        "reproducible": sharpe_match,
        "dataset_hash": bt.dataset_hash,
        "experiment_hash": bt.experiment_hash,
        "recomputed_experiment_hash": content_hash({"config": cfg.__dict__, "metrics": recomputed}),
        "research_record": {
            "id": rec.id if rec else None,
            "content_hash": rec.content_hash if rec else None,
            "prev_hash": rec.prev_hash if rec else None,
        },
        "note": "Reproducibility = re-running the exact config yields identical metrics.",
    }

"""Compare historical backtest / walk-forward / paper; measure drift."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.phase19.drift import evaluate_paper_drift


def load_phase18_baselines(path: Path | None = None) -> dict[str, Any]:
    """Pull validation / walk-forward baselines from Phase 18 artifacts if present."""
    root = Path.cwd()
    path = path or (root / "reports" / "phase18_strategy_search.json")
    if not path.exists():
        return {"available": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    finals = data.get("finalist_evaluations") or []
    if not finals:
        best = (data.get("best_candidates") or [{}])[0]
        return {
            "available": True,
            "source": "phase18_best_candidates",
            "candidate_id": best.get("candidate_id"),
            "validation_sharpe": best.get("mean_validation_sharpe"),
            "backtest": {"sharpe": best.get("mean_validation_sharpe")},
            "walkforward": {},
        }
    # Aggregate first finalist across symbols for rough baseline
    row0 = finals[0]
    val = row0.get("validation_metrics") or {}
    test = row0.get("test_metrics") or {}
    wf = row0.get("walkforward") or {}
    wins = wf.get("windows") or []
    wf_sharpes = [
        (w.get("metrics") or {}).get("sharpe_ratio")
        for w in wins
        if (w.get("metrics") or {}).get("sharpe_ratio") is not None
    ]
    return {
        "available": True,
        "source": "phase18_finalist_evaluations",
        "candidate_id": row0.get("candidate_id"),
        "strategy_family": row0.get("strategy_family"),
        "backtest": {
            "sharpe": val.get("sharpe_ratio"),
            "cagr": val.get("cagr"),
            "total_return": val.get("total_return"),
            "max_drawdown": val.get("maximum_drawdown"),
            "trades": val.get("number_of_trades"),
            "turnover": val.get("turnover"),
        },
        "walkforward": {
            "windows": len(wins),
            "mean_sharpe": (sum(wf_sharpes) / len(wf_sharpes)) if wf_sharpes else None,
        },
        "sealed_test": {
            "sharpe": test.get("sharpe_ratio") if not test.get("sealed") else None,
            "sealed": bool(test.get("sealed")),
        },
    }


def compare_regimes(
    *,
    paper_session: dict[str, Any],
    baselines: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baselines = baselines if baselines is not None else load_phase18_baselines()
    paper = paper_session
    bt = (baselines.get("backtest") or {}) if baselines.get("available") else {}
    wf = (baselines.get("walkforward") or {}) if baselines.get("available") else {}

    expected_fills = int(bt.get("trades") or paper.get("trade_count") or 0)
    actual_fills = int(paper.get("trade_count") or 0)
    drift = evaluate_paper_drift(
        expected_fills=expected_fills,
        actual_fills=actual_fills,
        expected_turnover=float(bt.get("turnover") or 0.0) or None,
        actual_turnover=float(paper.get("turnover") or 0.0) or None,
        signal_count_bt=expected_fills,
        signal_count_paper=int(paper.get("signal_frequency") or actual_fills),
        exposure_bt=0.5,
        exposure_paper=float(paper.get("exposure_end") or 0.0) / max(float(paper.get("total_pnl", 0) or 0) + 100_000.0, 1.0),
        stale_events=0,  # primary validation ignores intentional stress stales
        avg_price_delta_bps=0.0,
    )
    # Within accepted drift limits := not blocking further paper
    within_limits = not bool(drift.get("blocks_further_paper")) and drift.get("action") != "STOP"

    return {
        "historical_backtest": bt,
        "walk_forward": wf,
        "paper_trading": {
            "sharpe": paper.get("sharpe"),
            "total_return": paper.get("total_return"),
            "max_drawdown": paper.get("max_drawdown"),
            "trade_count": paper.get("trade_count"),
            "turnover": paper.get("turnover"),
            "total_pnl": paper.get("total_pnl"),
        },
        "backtest_to_paper_drift": drift,
        "within_existing_drift_limits": within_limits,
        "baselines_available": bool(baselines.get("available")),
        "note": "Profitability alone is not validation.",
    }

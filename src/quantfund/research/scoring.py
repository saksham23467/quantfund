"""Versioned ResearchScore policy (score_policy_v1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScoreConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str = "score_policy_v1"
    w_risk_adjusted: float = 0.30
    w_drawdown: float = 0.20
    w_cost_drag: float = 0.15
    w_consistency: float = 0.15
    w_robustness: float = 0.10
    w_integrity: float = 0.10
    min_excess_sharpe_vs_bh: float = -0.25


SCORE_POLICY_V1 = ScoreConfig()


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_research_score(
    *,
    oos_metrics: dict[str, Any],
    buyhold_metrics: dict[str, Any] | None,
    robustness_pass_rate: float | None,
    research_eligibility: str,
    n_trials: int,
    dsr: float | None,
    policy: ScoreConfig = SCORE_POLICY_V1,
) -> dict[str, Any]:
    """Explainable composite score on out-of-sample metrics.

    Returns dict with total and components. Hard rejects return accepted=False.
    """
    reasons: list[str] = []
    if research_eligibility == "development_only":
        reasons.append("development_only_dataset_cannot_be_accepted")

    sharpe = oos_metrics.get("sharpe_ratio")
    mdd = oos_metrics.get("maximum_drawdown")
    costs = float(oos_metrics.get("total_transaction_costs") or 0.0)
    turnover = float(oos_metrics.get("turnover") or 0.0)
    total_return = oos_metrics.get("total_return")

    bh_sharpe = None if not buyhold_metrics else buyhold_metrics.get("sharpe_ratio")
    excess_sharpe = None
    if sharpe is not None and bh_sharpe is not None:
        excess_sharpe = sharpe - bh_sharpe
        if excess_sharpe < policy.min_excess_sharpe_vs_bh:
            reasons.append("validation_excess_sharpe_below_threshold")

    # Component scores in [0, 100]
    if sharpe is None:
        risk_adj = 0.0
    else:
        risk_adj = _clip((sharpe + 1.0) / 3.0, 0, 1) * 100

    if mdd is None:
        dd_score = 50.0
    else:
        dd_score = _clip(1.0 - abs(mdd) / 0.5, 0, 1) * 100

    cost_score = _clip(1.0 - (costs / 1000.0) - 0.1 * turnover, 0, 1) * 100
    consistency = 50.0  # filled by runner when subperiod data available
    if oos_metrics.get("consistency_fraction") is not None:
        consistency = float(oos_metrics["consistency_fraction"]) * 100
    robustness = 50.0 if robustness_pass_rate is None else robustness_pass_rate * 100

    integrity = 100.0
    if research_eligibility == "development_only":
        integrity = 0.0
    elif n_trials > 1:
        integrity = _clip(1.0 - math_log_penalty(n_trials), 0, 1) * 100
        if dsr is not None:
            integrity = 0.5 * integrity + 0.5 * (dsr * 100)

    total = (
        policy.w_risk_adjusted * risk_adj
        + policy.w_drawdown * dd_score
        + policy.w_cost_drag * cost_score
        + policy.w_consistency * consistency
        + policy.w_robustness * robustness
        + policy.w_integrity * integrity
    )

    accepted = len(reasons) == 0 and research_eligibility != "development_only"
    return {
        "policy_id": policy.policy_id,
        "total": round(total, 4),
        "components": {
            "risk_adjusted": round(risk_adj, 4),
            "drawdown": round(dd_score, 4),
            "cost_drag": round(cost_score, 4),
            "consistency": round(consistency, 4),
            "robustness": round(robustness, 4),
            "integrity": round(integrity, 4),
        },
        "weights": policy.model_dump(),
        "accepted": accepted,
        "rejection_reasons": reasons,
        "excess_sharpe_vs_buyhold": excess_sharpe,
        "total_return": total_return,
    }


def math_log_penalty(n_trials: int) -> float:
    import math

    return min(0.9, math.log(max(n_trials, 1)) / 10.0)

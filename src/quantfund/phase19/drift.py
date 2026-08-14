"""Paper vs backtest drift — flag/stop per existing policy (no strategy mutation)."""

from __future__ import annotations

from typing import Any

from quantfund.phase11.drift_cert import (
    PaperDriftClass,
    classify_backtest_paper_drift,
)
from quantfund.research.drift import DriftSeverity, evaluate_drift


def evaluate_paper_drift(
    *,
    expected_fills: int,
    actual_fills: int,
    expected_turnover: float | None = None,
    actual_turnover: float | None = None,
    avg_price_delta_bps: float = 0.0,
    cost_delta_ratio: float = 0.0,
    signal_count_bt: int | None = None,
    signal_count_paper: int | None = None,
    exposure_bt: float | None = None,
    exposure_paper: float | None = None,
    stale_events: int = 0,
) -> dict[str, Any]:
    """Compare paper execution to historical/backtest assumptions."""
    bt_orders = expected_fills
    paper_orders = actual_fills
    sig_bt = signal_count_bt if signal_count_bt is not None else expected_fills
    sig_paper = signal_count_paper if signal_count_paper is not None else actual_fills

    report = classify_backtest_paper_drift(
        signal_count_bt=sig_bt,
        signal_count_paper=sig_paper,
        order_count_bt=bt_orders,
        order_count_paper=paper_orders,
        avg_price_delta_bps=avg_price_delta_bps,
        cost_delta_ratio=cost_delta_ratio,
    )

    baseline: dict[str, Any] = {
        "universe_size": 1,
        "turnover": expected_turnover or 0.0,
        "signal_frequency": float(sig_bt or 0),
        "exposure": exposure_bt or 0.0,
    }
    observed: dict[str, Any] = {
        "missing_feature_rate": 0.0,
        "turnover": actual_turnover if actual_turnover is not None else 0.0,
        "signal_frequency": float(sig_paper or 0),
        "exposure": exposure_paper if exposure_paper is not None else 0.0,
    }
    policy_report = evaluate_drift(baseline=baseline, observed=observed)

    action = "CONTINUE"
    if report.classification == PaperDriftClass.CRITICAL or report.blocks_further_paper:
        action = "STOP"
    elif report.classification == PaperDriftClass.WARNING:
        action = "FLAG"
    if policy_report.severity == DriftSeverity.HARD_FAIL:
        action = "STOP"
    elif policy_report.severity == DriftSeverity.WARNING and action == "CONTINUE":
        action = "FLAG"
    if stale_events > 0 and action == "CONTINUE":
        action = "FLAG"

    return {
        "classification": report.classification.value,
        "action": action,
        "blocks_further_paper": report.blocks_further_paper or action == "STOP",
        "findings": list(report.findings),
        "policy_severity": policy_report.severity.value,
        "policy_findings": [f.to_dict() for f in policy_report.findings],
        "expected_fills": expected_fills,
        "actual_simulated_fills": actual_fills,
        "avg_price_delta_bps": avg_price_delta_bps,
        "stale_events": stale_events,
        "strategy_mutated": False,
    }

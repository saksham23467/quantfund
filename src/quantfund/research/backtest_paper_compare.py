"""Explicit BACKTEST vs PAPER comparison with material-divergence flags.

Positive paper P&L alone never implies live eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_THRESHOLDS = {
    "return": 0.15,
    "sharpe": 1.0,
    "max_drawdown": 0.10,
    "turnover": 0.50,
    "trade_count_rel": 0.50,
    "win_rate": 0.20,
    "avg_trade_rel": 0.50,
    "costs_rel": 0.50,
    "slippage_bps": 25.0,
    "exposure": 0.25,
    "signal_frequency_rel": 0.50,
}


@dataclass
class BacktestPaperComparison:
    metrics: dict[str, dict[str, Any]]
    divergence_flags: list[str] = field(default_factory=list)
    material_divergence: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "divergence_flags": list(self.divergence_flags),
            "material_divergence": self.material_divergence,
            "notes": list(self.notes),
            "live_eligible_from_pnl_alone": False,
            "claims": "NONE",
        }


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _rel_diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    denom = max(abs(a), 1e-12)
    return abs(a - b) / denom


def compare_backtest_paper(
    backtest: dict[str, Any],
    paper: dict[str, Any],
    *,
    thresholds: dict[str, float] | None = None,
) -> BacktestPaperComparison:
    thr = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    keys = [
        "returns",
        "sharpe",
        "max_drawdown",
        "turnover",
        "trade_count",
        "win_rate",
        "average_trade",
        "transaction_costs",
        "slippage",
        "exposure",
        "signal_frequency",
        "execution_timing",
        "missed_fills",
        "rejected_orders",
    ]
    metrics: dict[str, dict[str, Any]] = {}
    flags: list[str] = []
    notes: list[str] = ["paper_pnl_positive_insufficient_for_live"]

    for k in keys:
        bt = backtest.get(k)
        pp = paper.get(k)
        metrics[k] = {"backtest": bt, "paper": pp}

    # Absolute / relative divergence checks
    bt_ret = _safe_float(backtest.get("returns"))
    pp_ret = _safe_float(paper.get("returns"))
    if bt_ret is not None and pp_ret is not None:
        if abs(bt_ret - pp_ret) > thr["return"]:
            flags.append("returns_divergence")

    bt_sh = _safe_float(backtest.get("sharpe"))
    pp_sh = _safe_float(paper.get("sharpe"))
    if bt_sh is not None and pp_sh is not None:
        if abs(bt_sh - pp_sh) > thr["sharpe"]:
            flags.append("sharpe_divergence")

    bt_dd = _safe_float(backtest.get("max_drawdown"))
    pp_dd = _safe_float(paper.get("max_drawdown"))
    if bt_dd is not None and pp_dd is not None:
        if abs(bt_dd - pp_dd) > thr["max_drawdown"]:
            flags.append("max_drawdown_divergence")

    bt_to = _safe_float(backtest.get("turnover"))
    pp_to = _safe_float(paper.get("turnover"))
    if bt_to is not None and pp_to is not None:
        if abs(bt_to - pp_to) > thr["turnover"]:
            flags.append("turnover_divergence")

    bt_tc = _safe_float(backtest.get("trade_count"))
    pp_tc = _safe_float(paper.get("trade_count"))
    rel_tc = _rel_diff(bt_tc, pp_tc)
    if rel_tc is not None and rel_tc > thr["trade_count_rel"]:
        flags.append("trade_count_divergence")

    bt_wr = _safe_float(backtest.get("win_rate"))
    pp_wr = _safe_float(paper.get("win_rate"))
    if bt_wr is not None and pp_wr is not None and abs(bt_wr - pp_wr) > thr["win_rate"]:
        flags.append("win_rate_divergence")

    rel_avg = _rel_diff(
        _safe_float(backtest.get("average_trade")),
        _safe_float(paper.get("average_trade")),
    )
    if rel_avg is not None and rel_avg > thr["avg_trade_rel"]:
        flags.append("average_trade_divergence")

    rel_cost = _rel_diff(
        _safe_float(backtest.get("transaction_costs")),
        _safe_float(paper.get("transaction_costs")),
    )
    if rel_cost is not None and rel_cost > thr["costs_rel"]:
        flags.append("transaction_costs_divergence")

    bt_slip = _safe_float(backtest.get("slippage"))
    pp_slip = _safe_float(paper.get("slippage"))
    if bt_slip is not None and pp_slip is not None:
        if abs(bt_slip - pp_slip) > thr["slippage_bps"]:
            flags.append("slippage_divergence")

    bt_exp = _safe_float(backtest.get("exposure"))
    pp_exp = _safe_float(paper.get("exposure"))
    if bt_exp is not None and pp_exp is not None:
        if abs(bt_exp - pp_exp) > thr["exposure"]:
            flags.append("exposure_divergence")

    rel_sig = _rel_diff(
        _safe_float(backtest.get("signal_frequency")),
        _safe_float(paper.get("signal_frequency")),
    )
    if rel_sig is not None and rel_sig > thr["signal_frequency_rel"]:
        flags.append("signal_frequency_divergence")

    if int(paper.get("missed_fills") or 0) > int(backtest.get("missed_fills") or 0):
        flags.append("missed_fills_increase")
    if int(paper.get("rejected_orders") or 0) > int(
        backtest.get("rejected_orders") or 0
    ):
        flags.append("rejected_orders_increase")

    # Timing label mismatch
    if backtest.get("execution_timing") and paper.get("execution_timing"):
        if backtest.get("execution_timing") != paper.get("execution_timing"):
            flags.append("execution_timing_mismatch")
            notes.append("execution_timing_differs")

    material = len(flags) > 0
    return BacktestPaperComparison(
        metrics=metrics,
        divergence_flags=flags,
        material_divergence=material,
        notes=notes,
    )

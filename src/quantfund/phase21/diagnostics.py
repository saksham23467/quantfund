"""No-trade diagnostics — explain zero signals / zero paper orders."""

from __future__ import annotations

from collections import Counter
from typing import Any


def build_no_trade_diagnostics(
    *,
    market_events: int,
    strategy_evaluations: int,
    signals_by_action: dict[str, int],
    risk_approved: int,
    risk_rejected: int,
    paper_orders: int,
    paper_fills: int,
    symbols_evaluated: list[str],
    bars_evaluated: int,
    strategy_errors: int,
    audit_rows: list[dict[str, Any]] | None = None,
    paper_candidate: bool,
    mode: str,
    warmup_hint: str | None = None,
) -> dict[str, Any]:
    buy = int(signals_by_action.get("BUY", 0))
    sell = int(signals_by_action.get("SELL", 0))
    hold = int(signals_by_action.get("HOLD", 0))
    total_signals = buy + sell + hold

    why: list[str] = []
    if not paper_candidate:
        why.append("PAPER_CANDIDATE=FALSE — running OBSERVATION/PAPER-SANDBOX only")
    if market_events == 0:
        why.append("no_market_events_received")
    if strategy_evaluations == 0 and market_events > 0:
        why.append("bars_received_but_no_strategy_evaluations_stale_or_session_block")
    if total_signals == 0 and strategy_evaluations > 0:
        why.append("strategy_emitted_no_signals_check_warmup_or_thresholds")
        if warmup_hint:
            why.append(warmup_hint)
    if buy + sell == 0 and hold > 0:
        why.append("only_HOLD_signals_no_actionable_buy_sell")
    if risk_approved == 0 and (buy + sell) > 0:
        why.append("actionable_signals_all_risk_rejected")
    if paper_orders == 0 and risk_approved == 0:
        why.append("no_risk_approved_signals_so_no_paper_orders")
    if paper_orders == 0 and risk_approved > 0:
        why.append("risk_approved_but_paper_orders_zero_engine_path_issue")
    if strategy_errors:
        why.append(f"strategy_evaluation_errors={strategy_errors}")

    # Reason frequency from audit
    reason_counts: Counter[str] = Counter()
    for row in audit_rows or []:
        reason_counts[str(row.get("signal_reason") or "unknown")] += 1

    return {
        "total_market_events": market_events,
        "total_strategy_evaluations": strategy_evaluations,
        "BUY_signals": buy,
        "SELL_signals": sell,
        "HOLD_signals": hold,
        "risk_approved_signals": risk_approved,
        "risk_rejected_signals": risk_rejected,
        "paper_orders": paper_orders,
        "paper_fills": paper_fills,
        "symbols_evaluated": list(symbols_evaluated),
        "bars_evaluated": bars_evaluated,
        "strategy_evaluation_errors": strategy_errors,
        "PAPER_CANDIDATE": paper_candidate,
        "mode": mode,
        "why_no_activity": why,
        "signal_reason_counts": dict(reason_counts),
        "note": (
            "Do NOT simply report PAPER_VALIDATED. "
            "Zero activity must be explained."
        ),
    }

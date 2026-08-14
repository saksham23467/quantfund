"""Explicit stability answers from metrics — no subjective judgement."""

from __future__ import annotations

from typing import Any


def answer_stability(
    *,
    leaderboard_row: dict[str, Any],
    annual_by_symbol: dict[str, dict[str, Any]],
    experiment_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rule-based answers for Phase 17B strategy stability checklist."""
    strat = leaderboard_row.get("strategy")
    mean_ret = leaderboard_row.get("mean_oos_return")
    mean_sharpe = leaderboard_row.get("mean_sharpe")
    robust = bool(leaderboard_row.get("robust"))
    accepted = int(leaderboard_row.get("accepted") or 0)
    stocks = int(leaderboard_row.get("stocks") or 0)

    # Profitable across stocks: count symbols with positive validation return
    per = [e for e in experiment_rows if e.get("strategy") == strat]
    pos_stocks = sum(
        1
        for e in per
        if ((e.get("validation_metrics") or {}).get("total_return") or 0) > 0
    )
    neg_stocks = sum(
        1
        for e in per
        if ((e.get("validation_metrics") or {}).get("total_return") or 0) < 0
    )

    # Years with positive buy-hold coverage across symbols (proxy for multi-year data)
    year_pos = 0
    year_total = 0
    for sym, cov in annual_by_symbol.items():
        for y, info in (cov.get("years") or {}).items():
            year_total += 1
            if (info.get("buy_hold_return") or 0) is not None:
                year_pos += 1  # data present
    years_available = sorted(
        {
            y
            for cov in annual_by_symbol.values()
            for y in (cov.get("years") or {})
        }
    )

    # Dependence on one stock: max |contrib| share of absolute returns
    rets = [
        float((e.get("validation_metrics") or {}).get("total_return") or 0.0)
        for e in per
    ]
    dependence = None
    if rets:
        abs_sum = sum(abs(r) for r in rets) or 1.0
        dependence = max(abs(r) for r in rets) / abs_sum

    # BH comparison on risk-adjusted: mean sharpe vs implied — use score rejection reasons
    beats_bh_risk_adj = None
    if per:
        # If any experiment has validation sharpe and bh sharpe
        diffs = []
        for e in per:
            s = (e.get("validation_metrics") or {}).get("sharpe_ratio")
            bh = (e.get("buy_and_hold_validation") or {}).get("sharpe_ratio")
            if s is not None and bh is not None:
                diffs.append(s - bh)
        if diffs:
            beats_bh_risk_adj = (sum(diffs) / len(diffs)) > 0

    fragile_any = any((e.get("robustness") or {}).get("fragile") for e in per)
    wf_ok = all((e.get("walkforward_windows") or 0) > 0 for e in per) if per else False

    return {
        "strategy": strat,
        "profitable_across_multiple_years_data_present": len(years_available) >= 3,
        "years_available": years_available,
        "profitable_across_multiple_stocks": pos_stocks >= 2 and stocks >= 2,
        "profitable_stock_count": pos_stocks,
        "losing_stock_count": neg_stocks,
        "survives_costs_slippage_robust_flag": robust and not fragile_any,
        "survives_walkforward_windows_present": wf_ok,
        "survives_robustness_not_fragile": not fragile_any,
        "survives_dsr_accounted": leaderboard_row.get("mean_dsr") is not None,
        "outperforms_buyhold_risk_adjusted_mean": beats_bh_risk_adj,
        "depends_heavily_on_one_stock": (
            dependence is not None and dependence >= 0.6
        ),
        "single_stock_dependence_ratio": dependence,
        "accepted_by_gates": accepted > 0,
        "mean_oos_return": mean_ret,
        "mean_sharpe": mean_sharpe,
    }

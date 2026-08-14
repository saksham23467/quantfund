"""Cross-symbol aggregation and leaderboard ranking (VALIDATION only)."""

from __future__ import annotations

import math
from typing import Any

from quantfund.phase18.seal import SealGuard, SealViolation


def _sharpe(metrics: dict[str, Any]) -> float | None:
    v = metrics.get("sharpe_ratio")
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def aggregate_candidate(
    *,
    candidate_id: str,
    strategy_family: str,
    parameters: dict[str, Any],
    per_symbol: list[dict[str, Any]],
    guard: SealGuard,
) -> dict[str, Any]:
    """Aggregate validation performance across symbols. Never ranks on TEST."""
    sharpes: list[float] = []
    returns: list[float] = []
    profitable = 0
    by_symbol: dict[str, Any] = {}

    for row in per_symbol:
        guard.assert_can_rank(row)
        if "test_metrics" in row:
            tm = row["test_metrics"]
            if isinstance(tm, dict) and any(
                k in tm for k in ("sharpe_ratio", "cagr", "total_return")
            ):
                if not guard.test_unlocked:
                    raise SealViolation(
                        "aggregate saw unlocked TEST metrics during ranking"
                    )
        val = row.get("validation_metrics") or {}
        sh = _sharpe(val)
        tr = val.get("total_return")
        sym = row["symbol"]
        by_symbol[sym] = {
            "validation_sharpe": sh,
            "validation_total_return": tr,
            "validation_max_drawdown": val.get("maximum_drawdown"),
            "validation_cagr": val.get("cagr"),
            "n_trades": val.get("number_of_trades"),
            "config_hash": row.get("config_hash"),
            "trial_id": row.get("trial_id"),
            "status": row.get("status"),
        }
        if sh is not None:
            sharpes.append(sh)
        if isinstance(tr, (int, float)) and math.isfinite(float(tr)):
            returns.append(float(tr))
            if float(tr) > 0:
                profitable += 1

    mean_sh = sum(sharpes) / len(sharpes) if sharpes else None
    disp = None
    if len(sharpes) >= 2:
        mu = mean_sh or 0.0
        disp = (sum((s - mu) ** 2 for s in sharpes) / len(sharpes)) ** 0.5

    best_sym = None
    worst_sym = None
    pairs = [
        (info.get("validation_sharpe"), sym)
        for sym, info in by_symbol.items()
        if info.get("validation_sharpe") is not None
    ]
    if pairs:
        pairs.sort(key=lambda x: float(x[0]))
        worst_sym = pairs[0][1]
        best_sym = pairs[-1][1]

    # Return correlation across symbols (pairwise on overlapping not available —
    # use correlation of validation total_returns vector vs itself rank proxy:
    # store dispersion of returns as correlation substitute note).
    corr_note = "per_symbol_validation_return_dispersion_only"
    ret_corr = None
    if len(returns) >= 2:
        mu = sum(returns) / len(returns)
        var = sum((r - mu) ** 2 for r in returns) / len(returns)
        ret_corr = {"return_variance": var, "note": corr_note}

    return {
        "candidate_id": candidate_id,
        "strategy_family": strategy_family,
        "parameters": parameters,
        "n_symbols": len(per_symbol),
        "mean_validation_sharpe": mean_sh,
        "validation_sharpe_dispersion": disp,
        "best_symbol": best_sym,
        "worst_symbol": worst_sym,
        "pct_profitable_symbols": (
            profitable / len(per_symbol) if per_symbol else None
        ),
        "return_dispersion": ret_corr,
        "per_symbol": by_symbol,
        "rank_metric": "mean_validation_sharpe",
        "test_used_for_ranking": False,
    }


def rank_leaderboard(aggregates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple:
        sh = row.get("mean_validation_sharpe")
        if sh is None:
            return (-1e18, row["candidate_id"])
        return (float(sh), row["candidate_id"])

    ordered = sorted(aggregates, key=key, reverse=True)
    out = []
    for i, row in enumerate(ordered, start=1):
        r = dict(row)
        r["rank"] = i
        out.append(r)
    return out

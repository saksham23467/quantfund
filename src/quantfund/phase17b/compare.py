"""Phase 17A vs 17B comparison — diagnostic stability check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.phase15.models import scrub_secrets


def _lb_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["strategy"]: r for r in (payload.get("leaderboard") or [])}


def compare_phase17a_17b(
    phase17a: dict[str, Any],
    phase17b: dict[str, Any],
) -> dict[str, Any]:
    a_lb = _lb_map(phase17a)
    b_lb = _lb_map(phase17b)
    strategies = sorted(set(a_lb) | set(b_lb))
    rows = []
    for s in strategies:
        a = a_lb.get(s) or {}
        b = b_lb.get(s) or {}
        def _diff(key: str) -> float | None:
            av, bv = a.get(key), b.get(key)
            if av is None or bv is None:
                return None
            try:
                return float(bv) - float(av)
            except (TypeError, ValueError):
                return None

        rows.append(
            {
                "strategy": s,
                "phase17a": {
                    "mean_oos_return": a.get("mean_oos_return"),
                    "mean_sharpe": a.get("mean_sharpe"),
                    "mean_max_dd": a.get("mean_max_dd"),
                    "trades": a.get("trades"),
                    "mean_dsr": a.get("mean_dsr"),
                    "robust": a.get("robust"),
                    "accepted": a.get("accepted"),
                    "stocks": a.get("stocks"),
                },
                "phase17b": {
                    "mean_oos_return": b.get("mean_oos_return"),
                    "mean_sharpe": b.get("mean_sharpe"),
                    "mean_max_dd": b.get("mean_max_dd"),
                    "trades": b.get("trades"),
                    "mean_dsr": b.get("mean_dsr"),
                    "robust": b.get("robust"),
                    "accepted": b.get("accepted"),
                    "stocks": b.get("stocks"),
                },
                "difference": {
                    "mean_oos_return": _diff("mean_oos_return"),
                    "mean_sharpe": _diff("mean_sharpe"),
                    "mean_max_dd": _diff("mean_max_dd"),
                    "trades": _diff("trades"),
                    "mean_dsr": _diff("mean_dsr"),
                },
            }
        )

    return scrub_secrets(
        {
            "note": "Diagnostic comparison only — not used to tune strategies or eligibility",
            "phase17a": {
                "combined_dataset_hash": (phase17a.get("dataset") or {}).get(
                    "combined_dataset_hash"
                ),
                "symbols": (phase17a.get("dataset") or {})
                .get("inventory", {})
                .get("symbols"),
                "accepted_count": (phase17a.get("acceptance") or {}).get("accepted_count"),
                "trial_count": phase17a.get("trial_count"),
            },
            "phase17b": {
                "combined_dataset_hash": (phase17b.get("dataset") or {}).get(
                    "combined_dataset_hash"
                ),
                "symbols": (phase17b.get("dataset") or {})
                .get("inventory", {})
                .get("symbols"),
                "accepted_count": (phase17b.get("acceptance") or {}).get("accepted_count"),
                "trial_count": phase17b.get("trial_count"),
            },
            "strategies": rows,
            "acceptance_stable_zero": (
                (phase17a.get("acceptance") or {}).get("accepted_count") == 0
                and (phase17b.get("acceptance") or {}).get("accepted_count") == 0
            ),
        }
    )


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_comparison(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(scrub_secrets(report), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

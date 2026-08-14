"""Strategy Marketplace / leaderboard — reads the REAL Phase 19 search report."""

from __future__ import annotations

import json

from quantfund_terminal.backend.app.config import REPORTS_DIR

_FAMILY_LABELS = {
    "trend_following": "Trend Following",
    "momentum": "Cross-Sectional Momentum",
    "mean_reversion": "Mean Reversion",
    "breakout": "Breakout",
    "volatility_regime": "Volatility / Regime",
}


def _read() -> dict:
    path = REPORTS_DIR / "phase19_strategy_search.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_leaderboard() -> dict:
    rep = _read()
    families = rep.get("families", list(_FAMILY_LABELS))
    ran = rep.get("ran_search", False)
    accepted_ids = rep.get("final_accepted_candidate_ids", [])
    records = rep.get("records", [])

    rows: list[dict] = []
    if records:
        for r in records:
            rows.append(
                {
                    "strategy": r.get("candidate_id") or r.get("name"),
                    "family": r.get("family"),
                    "cagr": r.get("cagr"),
                    "sharpe": r.get("sharpe"),
                    "max_drawdown": r.get("max_drawdown"),
                    "dsr": r.get("dsr"),
                    "status": r.get("funnel_outcome", "UNKNOWN"),
                }
            )
    else:
        # No search ran (fail-closed). Show the candidate families as BLOCKED,
        # never as accepted — honesty is the pitch.
        for fam in families:
            rows.append(
                {
                    "strategy": _FAMILY_LABELS.get(fam, fam),
                    "family": fam,
                    "cagr": None,
                    "sharpe": None,
                    "max_drawdown": None,
                    "dsr": None,
                    "status": "BLOCKED_PENDING_ELIGIBILITY",
                }
            )

    return {
        "ran_search": ran,
        "stopped_reason": rep.get("stopped_reason"),
        "families": families,
        "funnel": rep.get("funnel", {}),
        "gate_policy": rep.get("gate_policy", {}),
        "dsr_trial_count": rep.get("dsr_trial_count", 0),
        "accepted_count": len(accepted_ids),
        "accepted_ids": accepted_ids,
        "auto_promotion": rep.get("auto_promotion", {"enabled": False}),
        "prerequisite": rep.get("prerequisite", {}),
        "rows": rows,
        "safety": rep.get("safety", {}),
        "statement": rep.get(
            "statement",
            "Acceptance requires a research-eligible dataset; none exists yet, so "
            "zero strategies are accepted (fail-closed).",
        ),
    }

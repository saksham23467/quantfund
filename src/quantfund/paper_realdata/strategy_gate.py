"""Strategy-acceptance + research-eligibility gate for paper trading.

Never invents acceptance. A strategy may enter paper only if it was accepted by
the controlled Phase 19 research funnel (which itself is gated behind research
eligibility). This reads the authoritative Phase 19 report; a missing report or
zero accepted candidates fails closed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def check_strategy_acceptance(*, reports_dir: Path) -> dict[str, Any]:
    """Return the strategy-acceptance verdict from the Phase 19 research report."""
    report = _load_json(reports_dir / "phase19_strategy_search.json")
    if report is None:
        return {
            "strategy_accepted": False,
            "accepted_candidate_ids": [],
            "research_eligible": False,
            "ran_search": False,
            "blockers": ["phase19_strategy_search_report_missing"],
            "note": (
                "No Phase 19 strategy-research report found; no strategy can be "
                "accepted for paper trading."
            ),
        }

    accepted_ids = list(report.get("final_accepted_candidate_ids") or [])
    prereq = report.get("prerequisite") or {}
    research_eligible = bool(prereq.get("research_eligible"))
    ran_search = bool(report.get("ran_search"))
    accepted = len(accepted_ids) > 0

    blockers: list[str] = []
    if not research_eligible:
        blockers.append("research_eligibility_false")
    if not ran_search:
        blockers.append("strategy_search_did_not_run")
    if not accepted:
        blockers.append("zero_accepted_strategies")

    return {
        "strategy_accepted": accepted,
        "accepted_candidate_ids": accepted_ids,
        "research_eligible": research_eligible,
        "ran_search": ran_search,
        "blockers": blockers,
        "note": (
            "Strategy acceptance is inherited from the Phase 19 research funnel; "
            "it is never fabricated here."
        ),
    }

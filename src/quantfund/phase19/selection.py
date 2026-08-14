"""Select Phase 18 survivors for paper — never invent acceptance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PaperCandidate:
    candidate_id: str
    strategy_family: str
    parameters: dict[str, Any]
    research_accepted: bool
    rank: int | None
    mean_validation_sharpe: float | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "strategy_family": self.strategy_family,
            "parameters": dict(self.parameters),
            "research_accepted": self.research_accepted,
            "rank": self.rank,
            "mean_validation_sharpe": self.mean_validation_sharpe,
            "source": self.source,
        }


def load_phase18_search_report(path: Path | None = None) -> dict[str, Any]:
    root = Path.cwd()
    path = path or (root / "reports" / "phase18_strategy_search.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_phase18_leaderboard(path: Path | None = None) -> dict[str, Any]:
    root = Path.cwd()
    path = path or (root / "reports" / "phase18_leaderboard.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def accepted_from_phase18(report: dict[str, Any] | None = None) -> list[PaperCandidate]:
    """Only strategies that survived existing research gates (accepted > 0)."""
    report = report if report is not None else load_phase18_search_report()
    accepted_n = int((report.get("candidates") or {}).get("accepted") or 0)
    if accepted_n <= 0:
        return []
    out: list[PaperCandidate] = []
    for row in report.get("finalist_evaluations") or []:
        if row.get("decision") == "PASS":
            out.append(
                PaperCandidate(
                    candidate_id=str(row.get("candidate_id")),
                    strategy_family=str(row.get("strategy_family")),
                    parameters=dict(row.get("parameters") or {}),
                    research_accepted=True,
                    rank=None,
                    mean_validation_sharpe=None,
                    source="phase18_accepted",
                )
            )
    return out


def sandbox_shortlist_from_phase18(
    *,
    leaderboard: dict[str, Any] | None = None,
    n: int = 1,
) -> list[PaperCandidate]:
    """Non-eligible infrastructure shortlist from leaderboard (accepted may be 0)."""
    leaderboard = leaderboard if leaderboard is not None else load_phase18_leaderboard()
    rows = list(leaderboard.get("leaderboard") or [])[: max(0, n)]
    return [
        PaperCandidate(
            candidate_id=str(r.get("candidate_id")),
            strategy_family=str(r.get("strategy_family")),
            parameters=dict(r.get("parameters") or {}),
            research_accepted=False,
            rank=r.get("rank"),
            mean_validation_sharpe=r.get("mean_validation_sharpe"),
            source="phase18_leaderboard_sandbox_only",
        )
        for r in rows
    ]


def select_paper_strategy(
    *,
    allow_sandbox_demo: bool = True,
    search_report: dict[str, Any] | None = None,
    leaderboard: dict[str, Any] | None = None,
) -> tuple[PaperCandidate | None, str]:
    """Return (candidate, mode). Production paper requires research acceptance."""
    accepted = accepted_from_phase18(search_report)
    if accepted:
        return accepted[0], "PRODUCTION_PAPER_ELIGIBLE"
    if allow_sandbox_demo:
        short = sandbox_shortlist_from_phase18(leaderboard=leaderboard, n=1)
        if short:
            return short[0], "INFRASTRUCTURE_SANDBOX"
        # Fallback when Phase 18 artifacts missing
        return (
            PaperCandidate(
                candidate_id="p19_sandbox_buy_hold",
                strategy_family="buy_and_hold",
                parameters={"allocation": 0.5},
                research_accepted=False,
                rank=None,
                mean_validation_sharpe=None,
                source="phase19_fallback_sandbox",
            ),
            "INFRASTRUCTURE_SANDBOX",
        )
    return None, "BLOCKED_NO_ACCEPTED_STRATEGY"

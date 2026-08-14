"""Paper validation report assembly (Phase 10)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_paper_validation_report(
    *,
    research_eligibility: str,
    paper_eligible: bool,
    accepted_strategies: list[dict[str, Any]],
    paper_sessions: list[dict[str, Any]],
    paper_policy: dict[str, Any] | None,
    comparison: dict[str, Any] | None = None,
    drift: dict[str, Any] | None = None,
    live_eligibility_candidate: bool = False,
    live_trading: str = "DISABLED",
    real_orders: int = 0,
    claims: str = "NONE",
    blockers: list[str] | None = None,
    mode: str = "synthetic",
) -> dict[str, Any]:
    return {
        "phase": 10,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "research_eligibility": research_eligibility,
        "paper_eligible": paper_eligible,
        "accepted_strategies": accepted_strategies,
        "accepted_count": len(accepted_strategies),
        "paper_sessions": paper_sessions,
        "paper_sessions_completed": sum(
            1 for s in paper_sessions if s.get("state") in {"COMPLETED", "PASSED", "FAILED", "EVALUATED"}
            or s.get("completed")
        ),
        "paper_policy": paper_policy or {"verdict": "NOT_RUN"},
        "comparison": comparison,
        "drift": drift,
        "live_eligibility_candidate": live_eligibility_candidate,
        "live_eligibility": False,
        "live_trading": live_trading,
        "real_orders": real_orders,
        "claims": claims,
        "blockers": list(blockers or []),
        "notes": [
            "Research acceptance ≠ profitability guarantee",
            "Paper pass ≠ live authorization",
            "Live trading remains disabled",
            "Phase 11 (real broker) NOT started",
        ],
    }


def write_paper_validation_report(path: Path, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def format_paper_validation_summary(payload: dict[str, Any]) -> str:
    lines = [
        "PHASE 10 — Research-to-Paper Validation",
        "=" * 60,
        f"Research eligibility: {str(payload.get('research_eligibility', '')).upper()}",
        f"Paper eligible: {str(payload.get('paper_eligible')).upper()}",
        f"Accepted strategies: {payload.get('accepted_count', 0)}",
        f"Paper sessions completed: {payload.get('paper_sessions_completed', 0)}",
        f"Paper-policy result: {(payload.get('paper_policy') or {}).get('verdict', 'NOT_RUN')}",
        f"Live eligibility candidate: {str(payload.get('live_eligibility_candidate')).upper()}",
        f"Live eligibility: FALSE",
        f"Real orders: {payload.get('real_orders', 0)}",
        f"Claims: {payload.get('claims', 'NONE')}",
    ]
    if payload.get("blockers"):
        lines.append(f"Blockers: {', '.join(payload['blockers'][:8])}")
    lines.append("Phase 11 has NOT started.")
    return "\n".join(lines)

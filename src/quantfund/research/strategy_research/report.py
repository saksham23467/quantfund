"""Report assembly + I/O for controlled Phase 19 strategy research.

Produces the mandated funnel output and writes:
- reports/phase19_strategy_search.json
- docs/PHASE19_STRATEGY_RESEARCH.md

Never enables trading; embeds the fail-closed safety payload.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.phase17c.safety import safety_payload
from quantfund.research.strategy_research.framework import (
    StrategyResearchResult,
    utc_now_iso,
)


def build_report_payload(result: StrategyResearchResult) -> dict[str, Any]:
    funnel = result.funnel()
    return {
        "phase": "19",
        "stage": "controlled_strategy_research",
        "statement": (
            "Phase 19 controlled strategy research. Gated behind research "
            "eligibility. NO PAPER TRADING, NO LIVE TRADING, NO BROKER ORDERS, "
            "NO AUTO-PROMOTION."
        ),
        "generated_at": utc_now_iso(),
        "prerequisite": result.prerequisite.to_dict(),
        "ran_search": result.ran_search,
        "stopped_reason": result.stopped_reason,
        "families": result.families,
        "budget": result.budget,
        "gate_policy": result.gate_policy,
        "dsr_trial_count": result.trial_count,
        "funnel": funnel,
        "final_accepted_candidate_ids": result.accepted_ids(),
        "auto_promotion": {
            "enabled": False,
            "promoted_candidates": [],
            "note": "Best strategy is never auto-promoted; acceptance != activation.",
        },
        "records": [r.to_dict() for r in result.records],
        "safety": safety_payload(),
    }


def _md(payload: dict[str, Any]) -> str:
    f = payload["funnel"]
    pre = payload["prerequisite"]
    ran = payload["ran_search"]
    lines = [
        "# PHASE 19 — Controlled Strategy Research",
        "",
        payload["statement"],
        "",
        f"_Generated: {payload['generated_at']}_",
        "",
        "## Prerequisite: research eligibility",
        "",
        f"- `research_eligible = {str(pre['research_eligible']).lower()}`",
        f"- `phase18_research_eligible = {str(pre['phase18_research_eligible']).lower()}`",
        f"- `pit_universe_research_eligible = "
        f"{str(pre['pit_universe_research_eligible']).lower()}`",
        f"- `ran_search = {str(ran).lower()}`",
        f"- `stopped_reason = {payload['stopped_reason']}`",
        "",
    ]
    if pre["blockers"]:
        lines.append("### Prerequisite blockers")
        lines.append("")
        lines.extend(f"- `{b}`" for b in pre["blockers"])
        lines.append("")
    lines += [
        "## Funnel",
        "",
        "| Stage | Count |",
        "| --- | ---: |",
        f"| candidates tested | {f['candidates_tested']} |",
        f"| candidates rejected | {f['candidates_rejected']} |",
        f"| candidates passing validation | {f['candidates_passing_validation']} |",
        f"| candidates passing OOS | {f['candidates_passing_oos']} |",
        f"| candidates passing robustness | {f['candidates_passing_robustness']} |",
        f"| candidates passing DSR | {f['candidates_passing_dsr']} |",
        f"| **final accepted candidates** | **{f['final_accepted_candidates']}** |",
        "",
        f"DSR trial count (multiple-testing accounting): `{payload['dsr_trial_count']}`",
        "",
        "## Research budget",
        "",
        "```json",
        json.dumps(payload["budget"], indent=2, sort_keys=True),
        "```",
        "",
        "## Gate policy (inherited from campaign AcceptancePolicy; only stricter)",
        "",
        "```json",
        json.dumps(payload["gate_policy"], indent=2, sort_keys=True),
        "```",
        "",
        "## Auto-promotion",
        "",
        f"- enabled: `{str(payload['auto_promotion']['enabled']).lower()}`",
        f"- promoted candidates: `{payload['auto_promotion']['promoted_candidates']}`",
        f"- {payload['auto_promotion']['note']}",
        "",
        "## Strategy families",
        "",
    ]
    lines.extend(f"- `{fam}`" for fam in payload["families"])
    lines += [
        "",
        "## Safety",
        "",
        "```json",
        json.dumps(payload["safety"], indent=2, sort_keys=True),
        "```",
        "",
    ]
    if f["final_accepted_candidates"] == 0:
        lines += [
            "## Result",
            "",
            "Zero candidates accepted. This is a valid research result "
            "(fail closed). No strategy was promoted or traded.",
            "",
        ]
    return "\n".join(lines)


def write_reports(
    payload: dict[str, Any], *, json_path: Path, md_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_md(payload), encoding="utf-8")

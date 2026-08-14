"""Campaign report — machine JSON + human text."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_campaign_report_payload(
    *,
    campaign_id: str,
    config_hash: str,
    final_state: str,
    purpose: str,
    dataset_id: str,
    dataset_version: str,
    certified_eligibility: str,
    source_grade: str,
    calendar_verified: bool,
    universe_completeness: str,
    pool_stats: dict[str, int],
    trial_counts: dict[str, int],
    budgets: dict[str, int],
    screening_policy_id: str,
    walkforward_enabled: bool,
    walkforward_stats: dict[str, Any] | None,
    seal: dict[str, Any],
    acceptance_summary: dict[str, Any],
    score_policy_version: str,
    cost_model: str,
    slippage_model: str,
    selection_criterion: str,
    warnings: list[str],
    candidate_decisions: list[dict[str, Any]],
    dsr_notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    accepted = int(acceptance_summary.get("accepted_count", 0))
    claims = "NONE"
    if certified_eligibility == "development_only" or purpose == "exploratory_development":
        accepted = 0
        claims = "NONE"
    elif accepted > 0:
        claims = "RESEARCH_CANDIDATE_ONLY"  # never live profitability language

    return {
        "campaign_id": campaign_id,
        "config_hash": config_hash,
        "final_state": final_state,
        "purpose": purpose,
        "dataset": {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "eligibility": certified_eligibility,
            "source_grade": source_grade,
            "calendar_verified": calendar_verified,
            "universe_completeness": universe_completeness,
        },
        "candidates": pool_stats,
        "experiments": {
            "budget": budgets,
            "trial_counts": trial_counts,
        },
        "screening_policy_id": screening_policy_id,
        "walkforward_enabled": walkforward_enabled,
        "walkforward_stats": walkforward_stats,
        "walkforward_note": (
            None if walkforward_enabled else "walkforward_disabled"
        ),
        "seal": seal,
        "test_evaluation_count": len(seal.get("test_evaluation_log") or []),
        "acceptance": {
            **acceptance_summary,
            "accepted_count": accepted,
        },
        "candidate_decisions": candidate_decisions,
        "statistical_integrity": dsr_notes or {},
        "score_policy_version": score_policy_version,
        "cost_model": cost_model,
        "slippage_model": slippage_model,
        "selection_criterion": selection_criterion,
        "warnings": warnings,
        "claims": claims,
        "banner": (
            "INFRASTRUCTURE VALIDATION ONLY — not evidence of edge"
            if certified_eligibility == "development_only"
            else None
        ),
    }


def format_campaign_report_text(payload: dict[str, Any]) -> str:
    ds = payload["dataset"]
    lines = [
        "PHASE 6 — RESEARCH CAMPAIGN REPORT",
        "=================================",
        "",
        f"Campaign: {payload['final_state']}",
        f"campaign_id: {payload['campaign_id']}",
        f"config_hash: {payload['config_hash']}",
        f"purpose: {payload['purpose']}",
        "",
        "Dataset:",
        f"  {ds['dataset_id']} / {ds['dataset_version']}",
        f"  eligibility: {ds['eligibility']}",
        f"  source_grade: {ds['source_grade']}",
        f"  calendar_verified: {ds['calendar_verified']}",
        f"  universe_completeness: {ds['universe_completeness']}",
        "",
        "Candidates:",
    ]
    for k, v in sorted(payload["candidates"].items()):
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("Trials / budgets:")
    for k, v in sorted(payload["experiments"]["trial_counts"].items()):
        lines.append(f"  {k}: {v}")
    for k, v in sorted(payload["experiments"]["budget"].items()):
        lines.append(f"  budget_{k}: {v}")
    lines.extend(
        [
            "",
            f"Walk-forward enabled: {payload['walkforward_enabled']}",
            f"Walk-forward note: {payload.get('walkforward_note')}",
            f"TEST evaluations: {payload['test_evaluation_count']}",
            f"Sealed: {payload['seal'].get('sealed')}",
            "",
            f"Accepted: {payload['acceptance'].get('accepted_count', 0)}",
            f"Claims: {payload['claims']}",
            f"Score policy: {payload['score_policy_version']}",
            f"Cost model: {payload['cost_model']}",
            f"Slippage model: {payload['slippage_model']}",
            f"Selection criterion: {payload['selection_criterion']}",
            "",
        ]
    )
    if payload.get("banner"):
        lines.append(payload["banner"])
        lines.append("")
    if payload.get("warnings"):
        lines.append("Warnings:")
        for w in payload["warnings"]:
            lines.append(f"  - {w}")
    lines.append("")
    lines.append("No live trading. No brokers. No LLM. No profitability claim.")
    return "\n".join(lines) + "\n"


def write_campaign_report(path: Path, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / "campaign_report.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    text = format_campaign_report_text(payload)
    (path / "campaign_report.txt").write_text(text, encoding="utf-8")
    return path

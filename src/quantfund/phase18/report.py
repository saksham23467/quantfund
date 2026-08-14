"""Phase 18 report writers and demo console output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.data.ingest.checksums import hash_json
from quantfund.phase15.models import scrub_secrets


def write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = scrub_secrets(payload)
    text = json.dumps(clean, indent=2, sort_keys=True, default=str)
    path.write_text(text + "\n", encoding="utf-8")
    return hash_json(clean)


def format_demo(report: dict[str, Any]) -> str:
    ds = report.get("dataset") or {}
    cand = report.get("candidates") or {}
    best = report.get("best_candidates") or []
    gates = report.get("gates") or {}
    safety = report.get("safety") or {}
    lines = [
        "PHASE 18 STRATEGY RESEARCH",
        "",
        "Dataset:",
        f"  dataset hash: {ds.get('combined_hash')}",
        f"  symbols: {', '.join(ds.get('symbols') or [])}",
        f"  date range: {ds.get('start')} → {ds.get('end')}",
        "",
        "Candidates:",
        f"  generated: {cand.get('generated')}",
        f"  evaluated: {cand.get('evaluated')}",
        f"  rejected: {cand.get('rejected')}",
        f"  finalists: {cand.get('finalists')}",
        f"  accepted: {cand.get('accepted')}",
        "",
        "Best candidates:",
    ]
    for b in best[:5]:
        lines.append(
            f"  - {b.get('strategy_family')} {b.get('parameters')} "
            f"val_sharpe={b.get('mean_validation_sharpe')}"
        )
    if not best:
        lines.append("  (none)")
    lines.extend(
        [
            "",
            "TEST:",
            f"  sealed: {gates.get('test_sealed')}",
            f"  not accessed until final evaluation: {gates.get('test_not_used_for_ranking')}",
            "",
            f"Leakage: {gates.get('leakage')}",
            f"Walk-forward: {gates.get('walkforward')}",
            f"Robustness: {gates.get('robustness')}",
            f"DSR: {gates.get('dsr')}",
            f"Reproducibility: {gates.get('reproducibility')}",
            "",
            f"Accepted strategies: {cand.get('accepted', 0)}",
            f"Paper candidates: {cand.get('paper_candidates', 0)}",
            "",
            f"Broker writes: {safety.get('orders_submitted', 0)}",
            f"Live trading: {safety.get('live_trading', 'DISABLED')}",
            f"Paper trading: {safety.get('paper_trading', 'NOT_STARTED')}",
            f"Kill switch: {safety.get('kill_switch', 'ARMED')}",
            "",
            f"place_order_called == {safety.get('place_order_called', 0)}",
            f"orders_submitted == {safety.get('orders_submitted', 0)}",
            f"broker_write_capability == {safety.get('broker_write_capability', 'DISABLED')}",
            f"live_trading == {safety.get('live_trading', 'DISABLED')}",
            f"paper_trading == {safety.get('paper_trading', 'NOT_STARTED')}",
            f"kill_switch == {safety.get('kill_switch', 'ARMED')}",
        ]
    )
    return "\n".join(lines)


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ds = report.get("dataset") or {}
    cand = report.get("candidates") or {}
    gates = report.get("gates") or {}
    body = f"""# PHASE 18 — Controlled Strategy Research

## Status

Controlled fixed-grammar search over certified Zerodha historical packages.
**No live trading. No paper trading. Broker writes disabled. Kill switch armed.**

## Dataset

- Combined hash: `{ds.get('combined_hash')}`
- Symbols: {', '.join(ds.get('symbols') or [])}
- Range: {ds.get('start')} → {ds.get('end')}
- Eligibility: DEVELOPMENT_ONLY (unchanged)

## Search

- Mode: `{report.get('search_mode')}`
- Config hash: `{report.get('search_config_hash')}`
- Candidates generated: {cand.get('generated')}
- Evaluated: {cand.get('evaluated')}
- Finalists: {cand.get('finalists')}
- Accepted: {cand.get('accepted')}
- Paper candidates: {cand.get('paper_candidates')}

## Ranking policy

- Parameters selected on TRAIN; candidates ranked on VALIDATION only
- TEST sealed until finalist evaluation
- Existing `score_policy_v1` + DEVELOPMENT_ONLY gates (no new thresholds)
- Trial family: `{report.get('family_id')}` (counters not reset)

## Gates

| Gate | Result |
|------|--------|
| Leakage | {gates.get('leakage')} |
| Walk-forward | {gates.get('walkforward')} |
| Robustness | {gates.get('robustness')} |
| DSR | {gates.get('dsr')} |
| Reproducibility | {gates.get('reproducibility')} |
| TEST seal | {gates.get('test_sealed')} |

## Artifacts

- `reports/phase18_strategy_search.json`
- `reports/phase18_leaderboard.json`
- Experiment registry under `experiments/phase18/registry/`

## Safety

- place_order_called = 0
- orders_submitted = 0
- broker_write_capability = DISABLED
- live_trading = DISABLED
- paper_trading = NOT_STARTED
- kill_switch = ARMED
"""
    path.write_text(body, encoding="utf-8")

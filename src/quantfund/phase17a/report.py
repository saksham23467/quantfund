"""Markdown + console report for Phase 17A."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_markdown(payload: dict[str, Any]) -> str:
    inv = (payload.get("dataset") or {}).get("inventory") or {}
    lines = [
        "# PHASE 17A — Real Zerodha Strategy Validation",
        "",
        "## Prominence",
        "",
        str(payload.get("statement") or ""),
        "",
        f"- Result: `{payload.get('result')}`",
        f"- Provider: `{payload.get('provider')}`",
        f"- Data: `{payload.get('data')}`",
        f"- Combined dataset hash: `{(payload.get('dataset') or {}).get('combined_dataset_hash')}`",
        f"- Eligibility: `{payload.get('eligibility')}`",
        "",
        "## Dataset",
        "",
        f"- Packages: `{inv.get('package_count')}`",
        f"- Symbols: `{', '.join(inv.get('symbols') or [])}`",
        "",
    ]
    for p in inv.get("packages") or []:
        lines.append(
            f"- `{p.get('symbol')}`: id=`{p.get('dataset_id')}` "
            f"ver=`{p.get('dataset_version')}` bars=`{p.get('bars')}` "
            f"range=`{p.get('start')}`→`{p.get('end')}` hash=`{p.get('content_hash')}` "
            f"price_policy=`{p.get('price_policy')}`"
        )
    lines.extend(["", "## Corporate actions", ""])
    ca = payload.get("corporate_actions") or {}
    lines.append(f"- File: `{ca.get('file')}`")
    lines.append(f"- File hash: `{ca.get('file_hash')}`")
    lines.append("")
    lines.append("| symbol | events | known | unknown | coverage | blockers |")
    lines.append("|---|---:|---:|---:|---|---|")
    for row in ca.get("table") or []:
        lines.append(
            f"| {row.get('symbol')} | {row.get('events')} | {row.get('known')} | "
            f"{row.get('unknown')} | {row.get('coverage')} | "
            f"{';'.join(row.get('blockers') or [])} |"
        )
    lines.extend(["", "## Quality / calendar", ""])
    for s in payload.get("symbols") or []:
        q = s.get("quality") or {}
        cal = q.get("calendar") or {}
        lines.append(
            f"- `{s.get('symbol')}`: errors=`{q.get('errors')}` warnings=`{q.get('warnings')}` "
            f"blocked=`{q.get('data_blocked')}` missing_sessions=`{cal.get('missing_sessions')}` "
            f"coverage=`{cal.get('coverage_ratio')}`"
        )
    lines.extend(["", "## Leaderboard (ranked by VALIDATION score — not TEST)", ""])
    lines.append(
        "| Rank | Strategy | Stocks | Mean OOS Return | Sharpe | Max DD | Trades | DSR | Robust | Accepted |"
    )
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---|---:|")
    for r in payload.get("leaderboard") or []:
        lines.append(
            f"| {r.get('rank')} | {r.get('strategy')} | {r.get('stocks')} | "
            f"{r.get('mean_oos_return')} | {r.get('mean_sharpe')} | {r.get('mean_max_dd')} | "
            f"{r.get('trades')} | {r.get('mean_dsr')} | {r.get('robust')} | {r.get('accepted')} |"
        )
    lines.extend(
        [
            "",
            "## Walk-forward / Robustness / Leakage / Reproducibility",
            "",
            f"- Walk-forward: `{(payload.get('walk_forward') or {}).get('status')}`",
            f"- Robustness: `{(payload.get('robustness') or {}).get('status')}`",
            f"- Leakage: `{(payload.get('leakage') or {}).get('status')}`",
            f"- Future CA leakage: `{(payload.get('future_ca_leakage') or {}).get('status')}`",
            f"- Next-bar-open: `{(payload.get('next_bar_open') or {}).get('status')}`",
            f"- Reproducibility: `{(payload.get('reproducibility') or {}).get('status')}`",
            f"- Regime: `{(payload.get('regime_analysis') or {}).get('status')}`",
            f"- Trial count: `{payload.get('trial_count')}`",
            "",
            "## Acceptance",
            "",
            f"- Accepted count: `{(payload.get('acceptance') or {}).get('accepted_count')}`",
            f"- Rejected count: `{(payload.get('acceptance') or {}).get('rejected_count')}`",
            "",
            "## PAPER_CANDIDATE",
            "",
        ]
    )
    for pc in payload.get("paper_candidates") or []:
        lines.append(f"- `{json.dumps(pc, default=str)}`")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- orders_submitted: `{(payload.get('safety') or {}).get('orders_submitted')}`",
            f"- place_order_called: `{(payload.get('safety') or {}).get('place_order_called')}`",
            f"- broker_write_capability: `{(payload.get('safety') or {}).get('broker_write_capability')}`",
            f"- live_trading: `{(payload.get('safety') or {}).get('live_trading')}`",
            f"- kill_switch: `{(payload.get('safety') or {}).get('kill_switch')}`",
            "",
            "## Blockers",
            "",
            "- DEVELOPMENT_ONLY / non_exchange Zerodha provenance",
            "- Existing score_policy_v1 rejects development_only datasets",
            "- Calendar/PIT/universe completeness still required for RESEARCH_ELIGIBLE",
            "- No Zerodha eligibility shortcut",
            "",
            "> Historical strategy validation only. No broker order submission occurred.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def print_demo_banner(payload: dict[str, Any]) -> None:
    inv = (payload.get("dataset") or {}).get("inventory") or {}
    print("==================================================")
    print("QUANTFUND PHASE 17A")
    print("REAL ZERODHA STRATEGY VALIDATION")
    print("==================================================")
    print()
    print(f"Provider: {payload.get('provider')}")
    print(f"Data: {payload.get('data')}")
    print()
    print("Dataset:")
    print(f"  Combined hash: {(payload.get('dataset') or {}).get('combined_dataset_hash')}")
    print(f"  Packages: {inv.get('package_count')}")
    print(f"  Symbols: {', '.join(inv.get('symbols') or [])}")
    print()
    print("Corporate Actions:")
    for row in (payload.get("corporate_actions") or {}).get("table") or []:
        print(
            f"  {row.get('symbol')}: events={row.get('events')} "
            f"coverage={row.get('coverage')}"
        )
    print()
    print("Leaderboard (VALIDATION rank):")
    print("Strategy | OOS Return | Sharpe | Max DD | Trades | Robust | DSR | Accepted")
    for r in payload.get("leaderboard") or []:
        print(
            f"{r.get('strategy')} | {r.get('mean_oos_return')} | {r.get('mean_sharpe')} | "
            f"{r.get('mean_max_dd')} | {r.get('trades')} | {r.get('robust')} | "
            f"{r.get('mean_dsr')} | {r.get('accepted')}"
        )
    print()
    print(f"Walk-forward: {(payload.get('walk_forward') or {}).get('status')}")
    print(f"Robustness: {(payload.get('robustness') or {}).get('status')}")
    print(f"Leakage: {(payload.get('leakage') or {}).get('status')}")
    print(f"Reproducibility: {(payload.get('reproducibility') or {}).get('status')}")
    print(f"Research eligibility: {payload.get('eligibility')}")
    print(f"Accepted strategies: {(payload.get('acceptance') or {}).get('accepted_count')}")
    print(f"PAPER_CANDIDATE: {(payload.get('paper_candidates') or [{}])[0]}")
    print()
    s = payload.get("safety") or {}
    print("Broker:")
    print(f"  Write capability: {s.get('broker_write_capability')}")
    print(f"  Orders submitted: {s.get('orders_submitted')}")
    print(f"  place_order_called: {s.get('place_order_called')}")
    print(f"  Live trading: {s.get('live_trading')}")
    print(f"  Kill switch: {s.get('kill_switch')}")
    print()
    print("==================================================")
    print(f"RESULT: {payload.get('result')}")
    print("==================================================")


def write_docs(payload: dict[str, Any], path: Path) -> None:
    path.write_text(render_markdown(payload), encoding="utf-8")

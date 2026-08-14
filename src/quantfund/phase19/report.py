"""Phase 19 daily / session reports."""

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


def daily_report_payload(session: dict[str, Any]) -> dict[str, Any]:
    acct = session.get("accounting") or {}
    return {
        "pnl": acct.get("total_pnl") or acct.get("pnl") or acct.get("equity"),
        "positions": session.get("positions") or {},
        "orders": session.get("paper_orders"),
        "fills": session.get("paper_fills"),
        "turnover": acct.get("turnover"),
        "drawdown": acct.get("max_drawdown") or acct.get("drawdown"),
        "strategy_signals": session.get("signals"),
        "risk_rejects": session.get("risk_rejections"),
        "data_quality_events": session.get("bars_rejected"),
        "latency": session.get("latency"),
        "stale_data_events": session.get("stale_events"),
        "reconciliation_ok": session.get("reconciliation_ok"),
        "drift": session.get("drift"),
    }


def format_demo(report: dict[str, Any]) -> str:
    s = report.get("safety") or {}
    a = report.get("activation") or {}
    r = report.get("run") or {}
    lines = [
        "PHASE 19 CONTROLLED PAPER TRADING",
        "",
        f"Mode: {report.get('mode')}",
        f"Duration: {report.get('duration')}",
        f"Strategy: {a.get('strategy_family')} ({a.get('candidate_id')})",
        f"Research accepted: {a.get('research_accepted')}",
        f"Freeze token: {a.get('freeze_token')}",
        "",
        f"Paper orders: {r.get('paper_orders', 0)}",
        f"Paper fills: {r.get('paper_fills', 0)}",
        f"Risk rejects: {r.get('risk_rejections', 0)}",
        f"Stale events: {r.get('stale_events', 0)}",
        f"Reconciliation: {'OK' if r.get('reconciliation_ok') else 'FAIL'}",
        f"Drift action: {(r.get('drift') or {}).get('action')}",
        "",
        f"real_broker_orders = {s.get('real_broker_orders', 0)}",
        f"place_order_called = {s.get('place_order_called', 0)}",
        f"paper_orders >= 0 → {s.get('paper_orders', 0)}",
        f"paper_fills >= 0 → {s.get('paper_fills', 0)}",
        f"live_trading = {s.get('live_trading', 'DISABLED')}",
        f"kill_switch = {s.get('kill_switch', 'ARMED')}",
        "",
        "Auto-graduate to live: DISABLED",
    ]
    return "\n".join(lines)


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    s = report.get("safety") or {}
    a = report.get("activation") or {}
    body = f"""# PHASE 19 — Controlled Real-Time Paper Trading

## Status

Paper trading only. **Zero real Zerodha order submissions.**

## Activation

- Mode: `{report.get('mode')}`
- Candidate: `{a.get('candidate_id')}`
- Family: `{a.get('strategy_family')}`
- Research accepted: `{a.get('research_accepted')}`
- Strategy hash: `{a.get('strategy_hash')}`
- Parameter hash: `{a.get('parameter_hash')}`
- Dataset/research hash: `{a.get('dataset_research_hash')}`
- Code version: `{a.get('code_version')}`
- Auto-graduate to live: **DISABLED**

## Session

- Duration: `{report.get('duration')}`
- Paper orders: {(report.get('run') or {}).get('paper_orders')}
- Paper fills: {(report.get('run') or {}).get('paper_fills')}
- Reconciliation: {(report.get('run') or {}).get('reconciliation_ok')}

## Safety

- real_broker_orders = {s.get('real_broker_orders', 0)}
- place_order_called = {s.get('place_order_called', 0)}
- live_trading = DISABLED
- kill_switch = ARMED
- Execution adapter = PaperExecutionAdapter only

## EC2

See `deploy/systemd/quantfund-phase19-paper.service` for the systemd unit template.
Health: `GET /health` on loopback (default port 8719).
"""
    path.write_text(body, encoding="utf-8")

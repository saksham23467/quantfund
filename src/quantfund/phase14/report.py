"""Phase 14 daily / session report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.paper.models import state_hash


def build_phase14_report(payload: dict[str, Any]) -> dict[str, Any]:
    out = {
        "phase": 14,
        **payload,
        "research_eligibility": "DEVELOPMENT_ONLY",
        "live_trading": "DISABLED",
        "broker_submissions": 0,
        "live_orders": 0,
        "claims": "NONE",
    }
    out["report_hash"] = state_hash(out)
    return out


def write_phase14_report(payload: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_phase14_report(payload)
    json_path = out_dir / "phase14_session_report.json"
    txt_path = out_dir / "phase14_session_report.txt"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    mode = report.get("mode", "REAL_TIME_PAPER")
    lines = [
        "PHASE 14 SESSION REPORT",
        f"MODE = {mode}",
        f"DATA SOURCE = {report.get('data_source', 'YFINANCE / SIMULATED STREAM')}",
        "RESEARCH ELIGIBILITY = DEVELOPMENT_ONLY",
        "LIVE TRADING = DISABLED",
        "BROKER SUBMISSIONS = 0",
        "CLAIMS = NONE",
        f"Session: {report.get('session_id')}",
        f"Strategy: {report.get('strategy_id')}",
        f"Bars received: {report.get('bars_received')}",
        f"Bars rejected: {report.get('bars_rejected')}",
        f"Signals: {report.get('signals')}",
        f"Orders: {report.get('orders')}",
        f"Rejected orders: {report.get('rejected')}",
        f"Fills: {report.get('fills')}",
        f"Stale events: {report.get('stale_events')}",
        f"Reconciliation: {report.get('reconciliation')}",
        f"Health: {report.get('health_status')}",
        f"Kill switch: {report.get('kill_switch')}",
        f"Recovery: {report.get('recovery')}",
        f"Ending equity: {report.get('ending_equity')}",
        f"Report hash: {report['report_hash']}",
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "txt": txt_path}

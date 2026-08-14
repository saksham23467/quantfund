"""Phase 15 session report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.paper.models import state_hash
from quantfund.phase15.models import scrub_secrets


def build_phase15_report(payload: dict[str, Any]) -> dict[str, Any]:
    out = scrub_secrets(
        {
            "phase": 15,
            **payload,
            "research_eligibility": "DEVELOPMENT_ONLY",
            "live_trading": "DISABLED",
            "broker_submissions": 0,
            "live_orders": 0,
            "real_orders": 0,
            "claims": "NONE",
        }
    )
    out["report_hash"] = state_hash(out)
    return out


def write_phase15_report(payload: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_phase15_report(payload)
    json_path = out_dir / "phase15_session_report.json"
    txt_path = out_dir / "phase15_session_report.txt"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    lines = [
        "PHASE 15 SESSION REPORT",
        f"Market data: {report.get('market_data_mode', 'SIMULATED')}",
        "Shadow: ENABLED",
        f"Would orders: {report.get('would_orders', 0)}",
        f"Simulated fills/orders: {report.get('simulated_orders', 0)}",
        f"Would fills: {report.get('would_fills', 0)}",
        f"Data blocked: {report.get('data_blocked', 0)}",
        "Real orders: 0",
        "Broker submissions: 0",
        "Live trading: DISABLED",
        f"Kill switch: {report.get('kill_switch', 'ARMED')}",
        "Research eligibility: DEVELOPMENT_ONLY",
        f"Reconciliation: {report.get('reconciliation')}",
        f"Recovery: {report.get('recovery')}",
        "Claims: NONE",
        f"Report hash: {report['report_hash']}",
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "txt": txt_path}

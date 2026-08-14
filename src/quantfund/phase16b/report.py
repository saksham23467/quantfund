"""Phase 16B reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.paper.models import state_hash
from quantfund.phase15.models import scrub_secrets


def build_phase16b_report(payload: dict[str, Any]) -> dict[str, Any]:
    out = scrub_secrets(
        {
            "phase": "16B",
            **payload,
            "research_eligibility": "DEVELOPMENT_ONLY",
            "claims": "NONE",
            "note": (
                "This system is capable of submitting real broker orders only when "
                "the explicit live-canary activation gates are satisfied. Normal "
                "demos, tests, CI, paper, and shadow sessions never submit real orders."
            ),
        }
    )
    out["report_hash"] = state_hash(out)
    return out


def write_phase16b_report(payload: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_phase16b_report(payload)
    json_path = out_dir / "phase16b_session_report.json"
    txt_path = out_dir / "phase16b_session_report.txt"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    lines = [
        "PHASE 16B SESSION REPORT",
        f"Mode: {report.get('mode')}",
        f"Broker: {report.get('broker', 'MOCK')}",
        f"Activation: {report.get('activation')}",
        f"Strategy: {report.get('strategy')}",
        f"Risk: {report.get('risk')}",
        f"Reconciliation: {report.get('reconciliation')}",
        f"Kill switch: {report.get('kill_switch')}",
        f"Broker submission: {report.get('broker_submission')}",
        f"Live orders: {report.get('live_orders', 0)}",
        "Research eligibility: DEVELOPMENT_ONLY",
        f"Live trading: {report.get('live_trading')}",
        "Claims: NONE",
        f"Report hash: {report['report_hash']}",
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "txt": txt_path}

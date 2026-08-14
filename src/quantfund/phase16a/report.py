"""Phase 16A session / readiness report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.paper.models import state_hash
from quantfund.phase15.models import scrub_secrets


def build_phase16a_report(payload: dict[str, Any]) -> dict[str, Any]:
    out = scrub_secrets(
        {
            "phase": "16A",
            **payload,
            "research_eligibility": "DEVELOPMENT_ONLY",
            "live_trading": "DISABLED",
            "live_orders": 0,
            "order_submission": "NOT IMPLEMENTED",
            "write_capability": "DISABLED",
            "claims": "NONE",
            "final_result": "LIVE_TRADING_DISABLED",
        }
    )
    out["report_hash"] = state_hash(out)
    return out


def write_phase16a_report(payload: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_phase16a_report(payload)
    json_path = out_dir / "phase16a_session_report.json"
    txt_path = out_dir / "phase16a_session_report.txt"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    lines = [
        "PHASE 16A SESSION REPORT",
        f"Broker: {report.get('broker', 'ZERODHA/MOCK')}",
        f"Authentication: {report.get('authentication')}",
        f"Account read: {report.get('account_read')}",
        f"Positions read: {report.get('positions_read')}",
        f"Orders read: {report.get('orders_read')}",
        f"Trades read: {report.get('trades_read')}",
        f"Reconciliation: {report.get('reconciliation')}",
        f"Kill switch: {report.get('kill_switch')}",
        "Write capability: DISABLED",
        "Order submission: NOT IMPLEMENTED",
        "Live orders: 0",
        "Research eligibility: DEVELOPMENT_ONLY",
        "Live trading: DISABLED",
        "Claims: NONE",
        f"Final result: {report.get('final_result')}",
        f"Report hash: {report['report_hash']}",
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "txt": txt_path}

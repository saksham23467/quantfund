"""Phase 13 paper validation report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.paper.models import state_hash


def build_phase13_report(result: Any) -> dict[str, Any]:
    accounting = result.accounting.to_dict() if result.accounting else {}
    return {
        "phase": 13,
        "mode": "CONTROLLED_HISTORICAL_SIMULATION",
        "session_id": result.session_id,
        "strategy_id": result.strategy_id,
        "strategy_version": result.strategy_version,
        "dataset": result.dataset_label,
        "date_range": result.date_range,
        "data_source": result.data_source,
        "research_eligibility": "DEVELOPMENT_ONLY",
        "paper_eligible": result.paper_eligible,
        "paper_mode": "CONTROLLED HISTORICAL SIMULATION",
        "live_trading": "DISABLED",
        "claims": "NONE",
        "config_hash": result.config_hash,
        "orders": result.orders_count,
        "accepted_orders": result.accepted_orders,
        "rejected_orders": result.rejected_orders,
        "fills": result.fills_count,
        "turnover": accounting.get("turnover"),
        "fees": accounting.get("fees"),
        "slippage": accounting.get("slippage"),
        "initial_capital": result.initial_capital,
        "final_equity": accounting.get("equity"),
        "realized_pnl": accounting.get("realized_pnl"),
        "unrealized_pnl": accounting.get("unrealized_pnl"),
        "max_drawdown": accounting.get("max_drawdown"),
        "exposure": accounting.get("gross_exposure"),
        "reconciliation": "CLEAN" if result.reconciliation_ok else "FAILED",
        "replay_hash": result.replay_hash,
        "replay_identical": result.replay_identical,
        "drift": result.drift.to_dict() if result.drift else None,
        "kill_switch": result.kill_switch_state,
        "live_orders": 0,
        "broker_submissions": 0,
        "warnings": list(result.warnings),
        "data_quality_warnings": list(result.data_quality_warnings),
        "state": result.state,
    }


def write_phase13_report(result: Any, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_phase13_report(result)
    payload["report_hash"] = state_hash(payload)
    json_path = out_dir / "phase13_paper_report.json"
    txt_path = out_dir / "phase13_paper_report.txt"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    lines = [
        "PHASE 13 PAPER VALIDATION REPORT",
        f"Mode: CONTROLLED_HISTORICAL_SIMULATION",
        f"Session: {payload['session_id']}",
        f"Strategy: {payload['strategy_id']}@{payload['strategy_version']}",
        f"Data source: {payload['data_source']}",
        f"RESEARCH ELIGIBILITY: DEVELOPMENT_ONLY",
        f"PAPER MODE: CONTROLLED HISTORICAL SIMULATION",
        f"LIVE TRADING: DISABLED",
        f"CLAIMS: NONE",
        f"Paper eligible: {payload['paper_eligible']}",
        f"Orders: {payload['orders']}",
        f"Fills: {payload['fills']}",
        f"Rejected orders: {payload['rejected_orders']}",
        f"Final equity: {payload['final_equity']}",
        f"Reconciliation: {payload['reconciliation']}",
        f"Replay identical: {payload['replay_identical']}",
        f"Drift: {payload['drift']['classification'] if payload['drift'] else 'N/A'}",
        f"Kill switch: {payload['kill_switch']}",
        f"Live orders: 0",
        f"Broker submissions: 0",
        f"Report hash: {payload['report_hash']}",
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "txt": txt_path}

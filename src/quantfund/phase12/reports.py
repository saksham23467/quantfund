"""Phase 12 paper session / safety / drift reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.paper.models import state_hash
from quantfund.phase12.engine import ControlledPaperResult


def build_phase12_report(result: ControlledPaperResult) -> dict[str, Any]:
    session = result.session
    snap = session.snapshot if session else {}
    fills = session.fills if session else []
    total_fees = sum(float(getattr(f, "transaction_cost", 0.0) or 0.0) for f in fills)
    turnover = sum(
        abs(float(f.quantity) * float(f.price)) for f in fills
    )
    equity = snap.get("equity") or snap.get("total_equity")
    cash = snap.get("cash") or snap.get("cash_balance")
    return {
        "phase": 12,
        "session_id": result.session_id,
        "state": result.state.value,
        "research_eligibility": result.research_eligibility,
        "paper_eligible": result.paper_eligible,
        "research_paper_eligible": result.research_paper_eligible,
        "paper_orders": result.paper_orders,
        "paper_fills": result.paper_fills,
        "live_orders": result.live_orders,
        "broker_submissions": result.broker_submissions,
        "kill_switch": result.kill_switch_state,
        "reconciliation": "CLEAN" if result.reconciliation_ok else "FAILED",
        "state_hash": result.state_hash,
        "cash": cash,
        "equity": equity,
        "positions": snap.get("positions") or snap.get("position_list"),
        "turnover": turnover,
        "total_costs": total_fees,
        "claims": result.claims,
        "live_trading": result.live_trading,
        "execution_mode": "PAPER",
        "eligibility": result.eligibility.to_dict(),
        "drift": result.drift.to_dict() if result.drift else None,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
    }


def write_phase12_report(result: ControlledPaperResult, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_phase12_report(result)
    payload["report_hash"] = state_hash(payload)
    json_path = out_dir / "phase12_paper_report.json"
    txt_path = out_dir / "phase12_paper_report.txt"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    lines = [
        "PHASE 12 PAPER REPORT",
        f"Session: {payload['session_id']}",
        f"State: {payload['state']}",
        f"Research eligibility: {payload['research_eligibility']}",
        f"Paper eligibility: {payload['paper_eligible']}",
        f"Research paper eligible: {payload['research_paper_eligible']}",
        f"Paper orders: {payload['paper_orders']}",
        f"Paper fills: {payload['paper_fills']}",
        f"Live orders: {payload['live_orders']}",
        f"Broker submissions: {payload['broker_submissions']}",
        f"Kill switch: {payload['kill_switch']}",
        f"Reconciliation: {payload['reconciliation']}",
        f"Execution mode: PAPER",
        f"Live trading: DISABLED",
        f"Claims: NONE",
        f"Report hash: {payload['report_hash']}",
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "txt": txt_path}

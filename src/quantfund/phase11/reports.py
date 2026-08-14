"""Paper session reports (JSON + text)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantfund.paper.models import state_hash
from quantfund.phase11.trading_session import PaperTradingSession


@dataclass
class PaperSessionReport:
    payload: dict[str, Any]

    @property
    def report_hash(self) -> str:
        return state_hash(self.payload)

    def to_json(self) -> str:
        return json.dumps(self.payload, indent=2, sort_keys=True, default=str)

    def to_text(self) -> str:
        p = self.payload
        lines = [
            "=== PAPER SESSION REPORT ===",
            f"session_id: {p.get('session_id')}",
            f"strategy: {p.get('strategy_id')}",
            f"dataset: {p.get('dataset')}",
            f"configuration_hash: {p.get('configuration_hash')}",
            f"starting_capital: {p.get('starting_capital')}",
            f"ending_capital: {p.get('ending_capital')}",
            f"positions: {p.get('positions')}",
            f"trades: {p.get('paper_orders')}",
            f"fills: {p.get('paper_fills')}",
            f"turnover: {p.get('turnover')}",
            f"fees: {p.get('fees')}",
            f"slippage: {p.get('slippage')}",
            f"gross_pnl: {p.get('gross_pnl')}",
            f"net_pnl: {p.get('net_pnl')}",
            f"max_drawdown: {p.get('max_drawdown')}",
            f"risk_violations: {p.get('risk_violations')}",
            f"rejected_orders: {p.get('rejected_orders')}",
            f"reconciliation: {p.get('reconciliation_status')}",
            f"kill_switch: {p.get('kill_switch_status')}",
            f"data_quality_warnings: {p.get('data_quality_warnings')}",
            f"eligibility: {p.get('eligibility')}",
            f"Execution mode: PAPER",
            f"Live orders: 0",
            f"Live trading: DISABLED",
            f"report_hash: {self.report_hash}",
        ]
        return "\n".join(lines)


def build_paper_session_report(
    session: PaperTradingSession,
    *,
    strategy_id: str = "unknown",
    dataset: str = "unknown",
    configuration_hash: str = "sha256:unknown",
    risk_violations: int = 0,
    rejected_orders: int = 0,
    data_quality_warnings: list[str] | None = None,
) -> PaperSessionReport:
    fees = sum(f.transaction_cost for f in session.fills)
    slip = sum(abs(f.slippage_per_unit) * f.quantity for f in session.fills)
    ending = float(session.portfolio.portfolio.cash)
    # rough equity without marks
    for sym, pos in session.portfolio.portfolio.positions.items():
        ending += pos.quantity * (pos.average_entry_price or 0.0)
    starting = session.initial_cash
    net = ending - starting
    payload = {
        "session_id": session.session_id,
        "strategy_id": strategy_id,
        "dataset": dataset,
        "configuration_hash": configuration_hash,
        "starting_capital": starting,
        "ending_capital": ending,
        "positions": {
            s: p.quantity for s, p in session.portfolio.portfolio.positions.items()
        },
        "paper_orders": session.paper_orders,
        "paper_fills": session.paper_fills,
        "turnover": sum(f.quantity * f.price for f in session.fills),
        "fees": fees,
        "slippage": slip,
        "gross_pnl": net + fees,
        "net_pnl": net,
        "max_drawdown": None,
        "risk_violations": risk_violations,
        "rejected_orders": rejected_orders,
        "reconciliation_status": (
            "CLEAN"
            if session.last_reconcile and session.last_reconcile.ok
            else ("MISMATCH" if session.last_reconcile else "UNKNOWN")
        ),
        "kill_switch_status": (
            "TRIGGERED" if session.kill_switch.is_triggered else "ARMED"
        ),
        "data_quality_warnings": list(data_quality_warnings or []),
        "eligibility": (
            session.gate_decision.to_dict() if session.gate_decision else None
        ),
        "execution_mode": "PAPER",
        "live_orders": 0,
        "live_trading": "DISABLED",
        "connectivity": session.connectivity.value,
        "state": session.state.value,
    }
    return PaperSessionReport(payload=payload)


def write_paper_session_report(
    report: PaperSessionReport, *, out_dir: Path, stem: str = "paper_session_report"
) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / f"{stem}.json"
    tp = out_dir / f"{stem}.txt"
    jp.write_text(report.to_json(), encoding="utf-8")
    tp.write_text(report.to_text(), encoding="utf-8")
    return jp, tp

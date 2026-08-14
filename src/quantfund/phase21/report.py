"""Phase 21 daily + final qualification reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def daily_report(
    *,
    day: str,
    symbols: list[str],
    bars_received: int,
    signals: int,
    orders: int,
    fills: int,
    rejections: int,
    cash: float,
    equity: float,
    pnl: float,
    drawdown: float | None,
    exposure: float,
    turnover: float,
    fees: float,
    slippage: float,
    data_quality: dict[str, Any],
    reconciliation: str,
    strategy_hash: str,
    configuration_hash: str,
    market_sessions: int = 1,
) -> dict[str, Any]:
    return {
        "date": day,
        "market_sessions": market_sessions,
        "symbols": symbols,
        "bars_received": bars_received,
        "signals": signals,
        "orders": orders,
        "fills": fills,
        "rejections": rejections,
        "cash": cash,
        "equity": equity,
        "pnl": pnl,
        "drawdown": drawdown,
        "exposure": exposure,
        "turnover": turnover,
        "fees": fees,
        "slippage": slippage,
        "data_quality": data_quality,
        "reconciliation": reconciliation,
        "strategy_hash": strategy_hash,
        "configuration_hash": configuration_hash,
        "order_class": "PAPER_ORDER",
        "live_broker_orders": 0,
    }


def format_banner() -> str:
    return "\n".join(
        [
            "========================================",
            "LIVE_TRADING = DISABLED",
            "BROKER_WRITE = DISABLED",
            "PAPER_TRADING = ENABLED",
            "KILL_SWITCH = ARMED",
            "========================================",
        ]
    )


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    elig = report.get("eligibility") or {}
    diag = report.get("diagnostics") or {}
    sess = report.get("session_metrics") or {}
    lines = [
        "# PHASE 21 — Autonomous Real-Time Paper Trading Qualification",
        "",
        f"**Result:** `{report.get('result')}`",
        "",
        format_banner(),
        "",
        "## Distinctions",
        "",
        "- **PAPER_ORDER** — simulated via `PaperExecutionAdapter` only",
        "- **LIVE_BROKER_ORDER** — forbidden; count must remain 0",
        "",
        "## Strategy",
        "",
        f"- name: `{report.get('strategy') or elig.get('strategy_name')}`",
        f"- strategy_hash: `{report.get('strategy_hash') or elig.get('strategy_hash')}`",
        f"- configuration_hash: `{report.get('configuration_hash') or elig.get('configuration_hash')}`",
        f"- PAPER_CANDIDATE: `{elig.get('PAPER_CANDIDATE')}`",
        f"- reason: {elig.get('reason')}",
        f"- mode: `{elig.get('mode')}`",
        "",
        "## Runtime",
        "",
        f"- EC2 instance: `{report.get('ec2_instance')}`",
        f"- Zerodha data source: `{report.get('zerodha_data_source')}`",
        f"- trading days: {report.get('trading_days')}",
        f"- market events: {report.get('market_events')}",
        f"- signals: {report.get('signals')}",
        f"- paper orders: {report.get('paper_orders')}",
        f"- paper fills: {report.get('paper_fills')}",
        f"- risk rejections: {report.get('risk_rejections')}",
        "",
        "## Performance (informational — not a live-trading gate)",
        "",
        f"- P&L: {sess.get('total_pnl')}",
        f"- drawdown: {sess.get('max_drawdown')}",
        f"- Sharpe: {sess.get('sharpe')}",
        f"- turnover: {sess.get('turnover')}",
        f"- fees: {sess.get('fees')}",
        f"- slippage: {sess.get('slippage')}",
        "",
        "## Drift / Recovery",
        "",
        f"- backtest-paper drift: `{((report.get('drift') or {}).get('action'))}`",
        f"- restarts: {report.get('restarts')}",
        f"- recovery events: {report.get('recovery_events')}",
        f"- outages: {report.get('outages')}",
        f"- reconciliation: `{report.get('reconciliation')}`",
        "",
        "## Safety",
        "",
        f"- leakage: `{report.get('leakage')}`",
        f"- reproducibility: `{report.get('reproducibility')}`",
        f"- broker write calls: `{report.get('broker_write_calls')}`",
        f"- live orders: `{report.get('live_orders')}`",
        f"- kill switch: `{report.get('kill_switch')}`",
        "",
        "## No-trade diagnostics",
        "",
        "```json",
        json.dumps(diag, indent=2, default=str),
        "```",
        "",
        "## Blockers",
        "",
    ]
    for b in report.get("blockers") or []:
        lines.append(f"- {b}")
    if not report.get("blockers"):
        lines.append("- (none)")
    lines.extend(
        [
            "",
            f"_Generated {report.get('generated_at')}_",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def format_demo(report: dict[str, Any]) -> str:
    elig = report.get("eligibility") or {}
    return "\n".join(
        [
            format_banner(),
            f"RESULT={report.get('result')}",
            f"PAPER_CANDIDATE={elig.get('PAPER_CANDIDATE')}",
            f"strategy={elig.get('strategy_name')} hash={elig.get('strategy_hash')}",
            f"days={report.get('trading_days')} events={report.get('market_events')} "
            f"signals={report.get('signals')} paper_orders={report.get('paper_orders')} "
            f"fills={report.get('paper_fills')}",
            f"LIVE_BROKER_ORDERS={report.get('live_orders')} "
            f"place_order_called={((report.get('assertions') or {}).get('place_order_called'))}",
        ]
    )

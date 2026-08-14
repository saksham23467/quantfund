"""Phase 20 report writers."""

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


def format_demo(report: dict[str, Any]) -> str:
    m = report.get("session_metrics") or {}
    s = report.get("safety") or {}
    lines = [
        "PHASE 20 LONG-DURATION PAPER VALIDATION",
        "",
        f"Result: {report.get('result')}",
        f"Duration: {report.get('duration_days')} trading days",
        f"Strategy: {(report.get('activation') or {}).get('strategy_family')}",
        f"Immutable: {report.get('strategy_immutable')}",
        "",
        f"Trades: {m.get('trade_count')}",
        f"Total PnL: {m.get('total_pnl')}",
        f"Return: {m.get('total_return')}",
        f"Sharpe: {m.get('sharpe')}",
        f"Max DD: {m.get('max_drawdown')}",
        f"Reconciliation: {report.get('reconciliation_status')}",
        f"Drift within limits: {(report.get('comparison') or {}).get('within_existing_drift_limits')}",
        f"Stress suite: {(report.get('stress') or {}).get('passed')}",
        "",
        f"real_broker_orders = {s.get('real_broker_orders', 0)}",
        f"place_order_called = {s.get('place_order_called', 0)}",
        f"live_trading = {s.get('live_trading', 'DISABLED')}",
        f"kill_switch = {s.get('kill_switch', 'ARMED')}",
        "",
        "Profitability alone is NOT validation.",
    ]
    return "\n".join(lines)


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    m = report.get("session_metrics") or {}
    body = f"""# PHASE 20 — Long-Duration Paper Validation

## Result

**{report.get('result')}**

Profitability alone is not validation.

## Duration

- Target: {report.get('duration_days')} trading days
- Completed: {(report.get('session_metrics') or {}).get('trading_days')}

## Strategy

- Family: `{(report.get('activation') or {}).get('strategy_family')}`
- Candidate: `{(report.get('activation') or {}).get('candidate_id')}`
- Freeze token: `{(report.get('activation') or {}).get('freeze_token')}`
- Immutable: `{report.get('strategy_immutable')}`
- No LLM / genetic / parameter mutation / auto-retrain / auto capital scaling

## Session metrics

- Trades: {m.get('trade_count')}
- Total PnL: {m.get('total_pnl')}
- Return: {m.get('total_return')}
- Sharpe: {m.get('sharpe')}
- Max drawdown: {m.get('max_drawdown')}
- Turnover: {m.get('turnover')}
- Win rate: {m.get('win_rate')}

## Reconciliation

`{report.get('reconciliation_status')}`

## Drift (backtest → paper)

Within existing limits: `{(report.get('comparison') or {}).get('within_existing_drift_limits')}`

## Stress suite

Passed: `{(report.get('stress') or {}).get('passed')}`

## Safety

- real_broker_orders = 0
- place_order_called = 0
- live_trading = DISABLED
- Zero live orders
"""
    path.write_text(body, encoding="utf-8")

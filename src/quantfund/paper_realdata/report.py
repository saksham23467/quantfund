"""Preflight report I/O for real-market-data paper trading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _md(payload: dict[str, Any]) -> str:
    r = payload["report"]
    mode = payload["mode"]
    can_start = payload["can_start_paper_session"]
    lines = [
        "# Real-Market-Data Paper Trading — Preflight",
        "",
        payload["statement"],
        "",
        f"_Generated: {payload['generated_at']}_",
        "",
        "## Mode",
        "",
        f"- `DATA_SOURCE = {mode['DATA_SOURCE']}`",
        f"- `EXECUTION_MODE = {mode['EXECUTION_MODE']}`",
        f"- `BROKER_WRITES = {mode['BROKER_WRITES']}`",
        "",
        "## Architecture",
        "",
        " -> ".join(payload["architecture"]),
        "",
        "## Preflight report",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| zerodha_data_connected | {str(r['zerodha_data_connected']).lower()} |",
        f"| strategy_accepted | {str(r['strategy_accepted']).lower()} |",
        f"| paper_execution_enabled | {str(r['paper_execution_enabled']).lower()} |",
        f"| real_broker_writes_enabled | {str(r['real_broker_writes_enabled']).lower()} |",
        f"| kill_switch | {r['kill_switch']} |",
        f"| orders_submitted | {r['orders_submitted']} |",
        f"| place_order_called | {r['place_order_called']} |",
        "",
        "## Verdict",
        "",
        f"- `can_start_paper_session = {str(can_start).lower()}`",
        f"- `started_paper_session = {str(payload['started_paper_session']).lower()}`",
        f"- `stop_reason = {payload['stop_reason']}`",
        "",
    ]
    if payload.get("blockers"):
        lines += ["### Blockers", ""]
        lines += [f"- `{b}`" for b in payload["blockers"]]
        lines.append("")
    lines += [
        "## Gates NOT bypassed",
        "",
    ]
    lines += [f"- {g}" for g in payload.get("gates_not_bypassed", [])]
    lines += [
        "",
        "## Broker-write guard",
        "",
        "```json",
        json.dumps(payload["broker_write_guard"], indent=2, sort_keys=True),
        "```",
        "",
        "## Safety",
        "",
        "```json",
        json.dumps(payload["safety"], indent=2, sort_keys=True),
        "```",
        "",
        "**STOP — preflight only. No paper session was started.**",
        "",
    ]
    return "\n".join(lines)


def write_preflight_reports(
    payload: dict[str, Any], *, json_path: Path, md_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_md(payload), encoding="utf-8")

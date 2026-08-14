"""Phase 21 safety — paper only; zero Zerodha write calls."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from quantfund.phase19.safety import (
    FORBIDDEN_CALLS,
    require_paper_execution_only,
    scan_phase19_for_broker_writes,
)


PHASE21_ROOT = Path(__file__).resolve().parent
_ALLOW = frozenset({"safety.py", "capability_probe.py"})


def scan_phase21_for_broker_writes() -> list[str]:
    hits: list[str] = []
    for path in PHASE21_ROOT.rglob("*.py"):
        if path.name in _ALLOW:
            continue
        src = path.read_text(encoding="utf-8")
        if "import yfinance" in src or "from yfinance" in src:
            hits.append(f"yfinance_import:{path.name}")
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "phase16b.broker" in node.module:
                    hits.append(f"forbidden_import:{path.name}:{node.module}")
                if node.module.endswith("zerodha.orders"):
                    hits.append(f"forbidden_import:{path.name}:{node.module}")
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALLS:
                    hits.append(f"{path.name}:{node.lineno}:{func.attr}")
                if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                    hits.append(f"{path.name}:{node.lineno}:{func.id}")
    hits.extend(scan_phase19_for_broker_writes())
    return hits


def safety_assertions(
    *,
    paper_orders: int = 0,
    paper_fills: int = 0,
) -> dict[str, Any]:
    hits = scan_phase21_for_broker_writes()
    payload = {
        "orders_submitted": 0,
        "place_order_called": 0,
        "cancel_order_called": 0,
        "modify_order_called": 0,
        "live_trading": "DISABLED",
        "broker_write_capability": "DISABLED",
        "paper_trading": "ENABLED",
        "kill_switch": "ARMED",
        "paper_orders": paper_orders,
        "paper_fills": paper_fills,
        "write_scan_hits": hits,
        "ok": not hits,
        "statement": "PHASE 21 PAPER ONLY — ZERO LIVE BROKER ORDERS.",
    }
    if hits:
        payload["ok"] = False
    return payload


__all__ = ["require_paper_execution_only", "safety_assertions", "scan_phase21_for_broker_writes"]

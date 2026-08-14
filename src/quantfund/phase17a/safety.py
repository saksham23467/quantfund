"""Phase 17A safety — no broker writes."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


FORBIDDEN_CALLS = frozenset(
    {"place_order", "modify_order", "cancel_order", "exit_order", "basket_order"}
)


def scan_phase17a_for_writes() -> list[str]:
    root = Path(__file__).resolve().parent
    hits: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.endswith(".orders") or node.module.endswith(
                    "zerodha.adapter"
                ):
                    hits.append(f"forbidden_import:{path.name}:{node.module}")
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALLS:
                    if isinstance(func.value, ast.Name) and func.value.id == "self":
                        continue
                    hits.append(f"{path.name}:{node.lineno}:call_{func.attr}")
                if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                    hits.append(f"{path.name}:{node.lineno}:call_{func.id}")
    return hits


def safety_payload(*, place_order_called: int = 0, orders_submitted: int = 0) -> dict[str, Any]:
    hits = scan_phase17a_for_writes()
    return {
        "orders_submitted": orders_submitted,
        "place_order_called": place_order_called,
        "broker_write_capability": "DISABLED",
        "live_trading": "DISABLED",
        "kill_switch": "ARMED",
        "paper_trading": "NOT_STARTED",
        "write_scan_hits": hits,
        "ok": orders_submitted == 0 and place_order_called == 0 and not hits,
    }

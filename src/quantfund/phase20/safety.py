"""Phase 20 safety — zero live orders; reuse Phase 19 paper isolation."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from quantfund.phase19.safety import (
    FORBIDDEN_CALLS,
    require_paper_execution_only,
    safety_payload as _p19_safety,
    scan_phase19_for_broker_writes,
)


PHASE20_ROOT = Path(__file__).resolve().parent
_ALLOW = frozenset({"safety.py", "stress.py"})


def scan_phase20_for_broker_writes() -> list[str]:
    hits: list[str] = []
    for path in PHASE20_ROOT.rglob("*.py"):
        if path.name in _ALLOW:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "phase16b" in (node.module or "") and "broker" in (node.module or ""):
                    hits.append(f"forbidden_import:{path.name}:{node.module}")
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALLS:
                    hits.append(f"{path.name}:{node.lineno}:{func.attr}")
                if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                    hits.append(f"{path.name}:{node.lineno}:{func.id}")
    # Phase 19 must also remain clean (shared paper path)
    hits.extend(scan_phase19_for_broker_writes())
    return hits


def safety_payload(
    *,
    paper_orders: int = 0,
    paper_fills: int = 0,
) -> dict[str, Any]:
    base = _p19_safety(
        place_order_called=0,
        real_broker_orders=0,
        paper_orders=paper_orders,
        paper_fills=paper_fills,
    )
    hits = scan_phase20_for_broker_writes()
    base["write_scan_hits"] = hits
    base["phase"] = "20"
    base["ok"] = base["ok"] and not hits
    base["statement"] = "PHASE 20 PAPER VALIDATION — ZERO LIVE ORDERS."
    return base


__all__ = [
    "require_paper_execution_only",
    "safety_payload",
    "scan_phase20_for_broker_writes",
]

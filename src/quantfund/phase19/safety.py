"""Phase 19 broker safety — paper adapter only; zero real order submissions."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.phase12.isolation import assert_paper_only_adapter, live_order_count_always_zero


PHASE19_ROOT = Path(__file__).resolve().parent

FORBIDDEN_CALLS = frozenset(
    {
        "place_order",
        "modify_order",
        "cancel_order",
        "exit_order",
        "basket_order",
        "place_gtt",
    }
)

FORBIDDEN_ADAPTER_TYPES = frozenset(
    {
        "ZerodhaCanaryBroker",
        "LiveBroker",
        "WriteBroker",
        "ZerodhaExecutionAdapter",
        "BrokerExecutionAdapter",
        "CanarySession",
    }
)

# Files that may mention forbidden names for guards / type rejection
_SCAN_ALLOWLIST = frozenset({"safety.py", "capability.py"})


def scan_phase19_for_broker_writes() -> list[str]:
    hits: list[str] = []
    for path in PHASE19_ROOT.rglob("*.py"):
        if path.name in _SCAN_ALLOWLIST:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "phase16b" in node.module and "broker" in node.module:
                    hits.append(f"forbidden_import:{path.name}:{node.module}")
                if node.module.endswith("zerodha.orders") or node.module.endswith(
                    "zerodha.adapter"
                ):
                    hits.append(f"forbidden_import:{path.name}:{node.module}")
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALLS:
                    hits.append(f"{path.name}:{node.lineno}:call_{func.attr}")
                if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                    hits.append(f"{path.name}:{node.lineno}:call_{func.id}")
    return hits


def reject_forbidden_adapter(adapter: Any) -> None:
    name = type(adapter).__name__
    if name in FORBIDDEN_ADAPTER_TYPES:
        raise RuntimeError(f"forbidden_execution_adapter:{name}")
    # Capability flags if present
    if getattr(adapter, "can_place_orders", False) is True:
        raise RuntimeError(f"adapter_can_place_orders:{name}")
    caps = getattr(adapter, "capabilities", None)
    if callable(caps):
        c = caps()
        if getattr(c, "place_order", False) or getattr(c, "can_place_orders", False):
            raise RuntimeError(f"adapter_write_capability:{name}")


def require_paper_execution_only(adapter: Any) -> PaperExecutionAdapter:
    reject_forbidden_adapter(adapter)
    return assert_paper_only_adapter(adapter)


def safety_payload(
    *,
    place_order_called: int = 0,
    real_broker_orders: int = 0,
    paper_orders: int = 0,
    paper_fills: int = 0,
) -> dict[str, Any]:
    hits = scan_phase19_for_broker_writes()
    live_order_count_always_zero(live_orders=real_broker_orders)
    return {
        "real_broker_orders": real_broker_orders,
        "place_order_called": place_order_called,
        "paper_orders": paper_orders,
        "paper_fills": paper_fills,
        "live_trading": "DISABLED",
        "kill_switch": "ARMED",
        "broker_write_capability": "DISABLED",
        "paper_trading": "INFRASTRUCTURE_SANDBOX",
        "allowed_execution_adapter": "PaperExecutionAdapter",
        "write_scan_hits": hits,
        "ok": (
            real_broker_orders == 0
            and place_order_called == 0
            and not hits
        ),
        "statement": "PHASE 19 PAPER ONLY — ZERO REAL ZERODHA ORDERS.",
    }

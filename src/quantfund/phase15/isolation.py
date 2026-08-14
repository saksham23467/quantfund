"""Phase 15 isolation — prove no write-capable broker / REAL_ORDER path."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from quantfund.phase15.broker_readonly import (
    BrokerWriteForbidden,
    ReadOnlyBrokerAdapter,
    SimulatedReadOnlyBroker,
)
from quantfund.phase15.capabilities import BrokerCapabilities


PHASE15_ROOT = Path(__file__).resolve().parent


def place_order_call_count_guard(broker: ReadOnlyBrokerAdapter) -> int:
    """Attempt place_order; must raise and never succeed. Returns 0 on block."""
    try:
        broker.place_order(symbol="RELIANCE", qty=1)  # type: ignore[misc]
    except BrokerWriteForbidden:
        return 0
    raise AssertionError("place_order must not succeed")


def assert_broker_write_methods_fail(broker: ReadOnlyBrokerAdapter | None = None) -> dict[str, Any]:
    broker = broker or SimulatedReadOnlyBroker()
    assert broker.can_place_orders is False
    caps = broker.capabilities()
    assert caps.place_order is False
    assert caps.cancel_order is False
    assert caps.modify_order is False
    assert caps.can_place_orders is False
    called = {"place_order": 0, "cancel_order": 0, "modify_order": 0}
    for name in called:
        try:
            getattr(broker, name)()
            called[name] += 1
        except BrokerWriteForbidden:
            pass
    if any(v > 0 for v in called.values()):
        raise AssertionError(f"write_methods_succeeded:{called}")
    return {"place_order_called": 0, "cancel_order_called": 0, "modify_order_called": 0}


def cannot_construct_write_capable_broker() -> None:
    try:
        BrokerCapabilities(
            provider_id="evil",
            authenticated=True,
            account_read=True,
            positions_read=True,
            orders_read=True,
            trades_read=True,
            place_order=True,
        )
    except ValueError as exc:
        if "write" in str(exc).lower() or "forbidden" in str(exc).lower():
            return
        raise
    raise AssertionError("write_capable_broker_constructed")


def scan_phase15_for_broker_submit_calls() -> list[str]:
    """AST scan — forbid place_order / kite.place_order style calls in phase15."""
    forbidden_attr = {"place_order", "place_gtt", "modify_order", "cancel_order"}
    hits: list[str] = []
    for path in PHASE15_ROOT.rglob("*.py"):
        if path.name == "isolation.py":
            # isolation intentionally references names for guards
            continue
        if path.name == "broker_readonly.py":
            # defines forbidden stubs that raise
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in forbidden_attr:
                    hits.append(f"{path.name}:{node.lineno}:{func.attr}")
                if isinstance(func, ast.Name) and func.id in forbidden_attr:
                    hits.append(f"{path.name}:{node.lineno}:{func.id}")
    return hits


def live_trading_invariant() -> dict[str, Any]:
    return {
        "LIVE_TRADING": False,
        "real_orders": 0,
        "broker_submissions": 0,
        "can_place_orders": False,
    }


def assert_no_secrets_in_text(text: str, secrets: list[str]) -> None:
    for s in secrets:
        if s and s in text:
            raise AssertionError("secret_leaked_into_artifact")

"""Phase 16A isolation — prove write paths unreachable."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from quantfund.phase15.broker_readonly import BrokerWriteForbidden
from quantfund.phase15.capabilities import BrokerCapabilities
from quantfund.phase16a.capabilities import (
    BrokerCapabilityFlag,
    DeclaredBrokerCapabilities,
    WRITE_FLAGS,
    assert_no_write_flags,
)
from quantfund.phase16a.zerodha_readonly import ZerodhaReadOnlyBroker, build_zerodha_readonly_broker


PHASE16A_ROOT = Path(__file__).resolve().parent

FORBIDDEN_IMPORTS = frozenset(
    {
        "quantfund.brokers.zerodha.adapter",
        "kiteconnect",
    }
)


def assert_write_methods_fail(broker: ZerodhaReadOnlyBroker | None = None) -> dict[str, int]:
    broker = broker or build_zerodha_readonly_broker(force_mock=True)
    called = {"place_order": 0, "cancel_order": 0, "modify_order": 0}
    for name in called:
        try:
            getattr(broker, name)()
            called[name] += 1
        except BrokerWriteForbidden:
            pass
    if any(v > 0 for v in called.values()):
        raise AssertionError(f"write_methods_succeeded:{called}")
    assert broker.can_place_orders is False
    return {"place_order_called": 0, "cancel_order_called": 0, "modify_order_called": 0}


def cannot_construct_write_capable_declarations() -> None:
    try:
        DeclaredBrokerCapabilities(
            provider_id="evil",
            flags=frozenset({BrokerCapabilityFlag.WRITE_PLACE_ORDER}),
        )
    except ValueError:
        return
    raise AssertionError("write_capable_declaration_constructed")


def cannot_construct_phase15_write_caps() -> None:
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
    except ValueError:
        return
    raise AssertionError("phase15_write_caps_constructed")


def scan_phase16a_for_broker_submit_calls() -> list[str]:
    forbidden_attr = {"place_order", "place_gtt", "modify_order", "cancel_order"}
    hits: list[str] = []
    for path in PHASE16A_ROOT.rglob("*.py"):
        if path.name in {"isolation.py", "zerodha_readonly.py"}:
            # defines forbidden stubs / guards
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
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_IMPORTS:
                        hits.append(f"{path.name}:import:{alias.name}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module in FORBIDDEN_IMPORTS:
                    hits.append(f"{path.name}:from:{node.module}")
                if node.module == "quantfund.brokers.zerodha.orders":
                    for alias in node.names:
                        if alias.name in forbidden_attr:
                            hits.append(f"{path.name}:from_orders:{alias.name}")
    return hits


def live_order_invariant() -> dict[str, Any]:
    return {
        "LIVE_TRADING": False,
        "live_orders": 0,
        "order_submission": "NOT IMPLEMENTED",
        "write_capability": "DISABLED",
        "can_place_orders": False,
    }


def assert_no_secrets_in_text(text: str, secrets: list[str]) -> None:
    for s in secrets:
        if s and s in text:
            raise AssertionError("secret_leaked_into_artifact")


def capability_downgrade_fail_closed() -> None:
    assert_no_write_flags([BrokerCapabilityFlag.READ_ACCOUNT])
    try:
        assert_no_write_flags(list(WRITE_FLAGS))
    except ValueError:
        return
    raise AssertionError("write_flags_accepted")

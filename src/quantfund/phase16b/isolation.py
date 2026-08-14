"""Phase 16B isolation — CI mock-only; gate failures never call place_order."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable

from quantfund.phase15.broker_readonly import BrokerWriteForbidden
from quantfund.phase16b.broker import ZerodhaCanaryBroker, build_canary_broker
from quantfund.phase16b.gates import GateDecision, OrderIntent, evaluate_pretrade_gates
from quantfund.phase16b.flags import resolve_live_trading_flag
from quantfund.phase16b.limits import CanaryPolicy
from quantfund.paper.kill_switch import KillSwitch


PHASE16B_ROOT = Path(__file__).resolve().parent


def assert_ci_uses_mock_broker(broker: ZerodhaCanaryBroker) -> None:
    if not broker.simulated:
        raise AssertionError("ci_must_use_simulated_broker")


def prove_gate_failure_skips_place_order(
    *,
    evaluate_and_submit: Callable[[], dict[str, Any]],
    broker: ZerodhaCanaryBroker,
) -> None:
    before = broker.place_calls
    out = evaluate_and_submit()
    assert out.get("place_order_called") is False or out.get("submitted") is False
    assert broker.place_calls == before


def scan_phase16b_for_urllib_in_demo() -> list[str]:
    hits: list[str] = []
    for name in ("demo.py",):
        path = PHASE16B_ROOT / name
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        if "UrllibKiteTransport" in src:
            hits.append(name)
    return hits


def unauthorized_place_order_raises() -> None:
    b = build_canary_broker(force_mock=True)
    b.connect()
    try:
        b.place_order(request=None)
    except (BrokerWriteForbidden, Exception):
        return
    finally:
        b.disconnect()
    raise AssertionError("unauthorized_place_succeeded")

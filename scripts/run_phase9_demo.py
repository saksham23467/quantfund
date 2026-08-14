#!/usr/bin/env python3
"""Phase 9 execution-gateway demo — DRY_RUN + MockBroker only.

Never sends real orders. Never uses real credentials.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.execution.broker_adapter import assert_mock_only
from quantfund.execution.gateway import ExecutionGateway, ExecutionMode, GatewayConfig
from quantfund.execution.live_eligibility import LiveAuthorization
from quantfund.execution.live_orders import BrokerOrderState
from quantfund.execution.mock_broker import MockBehavior
from quantfund.trading.models import Order, OrderSide, OrderType


def main() -> int:
    print("PHASE 9 — Execution gateway (DRY_RUN / MockBroker)")
    print("=" * 60)

    # Safety: only mock allowed
    assert_mock_only("mock")

    cfg = GatewayConfig(
        session_id="phase9_demo",
        mode=ExecutionMode.DRY_RUN,
        broker_adapter_id="mock",
        certified_eligibility="development_only",
        research_accepted=False,
        paper_eligible=False,
        mock_behavior=MockBehavior.FILL,
        strategy_id="phase9_demo_strategy",
    )
    gw = ExecutionGateway(cfg)
    elig = gw.start()

    # Attempt authorized path — must block
    order = Order(
        timestamp=datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc),
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=5,
        order_type=OrderType.MARKET,
    )
    blocked = gw.submit_order(order, intent_id="demo_blocked", ref_price=100.0)
    assert blocked.accepted is False

    # Infrastructure exercise of DRY_RUN mechanics (explicitly not live-authorized)
    exercised = gw.submit_order(
        order,
        intent_id="demo_dry_run_exercise",
        ref_price=100.0,
        require_live_authorized=False,
        require_operator=False,
    )
    assert exercised.dry_run is True
    assert gw.real_orders_sent == 0

    # Kill switch freeze
    gw.activate_kill_switch(reason="demo_freeze", actor="phase9_demo")
    frozen = gw.submit_order(
        order,
        intent_id="demo_frozen",
        ref_price=100.0,
        require_live_authorized=False,
        require_operator=False,
    )
    assert frozen.reason == "kill_switch"

    # Reset kill for reconcile of prior fill (demo only)
    gw.kill_switch.reset(reason="demo_reconcile", actor="phase9_demo")
    gw._blocked = False
    report = gw.reconcile()

    # Idempotency / UNKNOWN path
    gw2 = ExecutionGateway(
        GatewayConfig(
            session_id="phase9_demo_unknown",
            mock_behavior=MockBehavior.TIMEOUT_UNKNOWN,
            certified_eligibility="development_only",
        )
    )
    gw2.start()
    unk = gw2.submit_order(
        order,
        intent_id="unk",
        ref_price=100.0,
        require_live_authorized=False,
        require_operator=False,
    )
    assert unk.state == BrokerOrderState.UNKNOWN
    retry = gw2.submit_order(
        order,
        intent_id="unk",
        ref_price=100.0,
        require_live_authorized=False,
        require_operator=False,
    )
    assert retry.accepted is False

    summary = gw.stop()
    gw2.stop()

    mock_pass = gw.broker.adapter_id == "mock" and gw.real_orders_sent == 0
    dry_pass = all(r.dry_run for r in gw.transport.responses) and exercised.dry_run
    idem_pass = retry.accepted is False
    recon_pass = report.ok
    kill_pass = frozen.reason == "kill_switch"
    auth_pass = (
        elig.authorization == LiveAuthorization.LIVE_BLOCKED
        and elig.live_eligible is False
    )

    ok = all([mock_pass, dry_pass, idem_pass, recon_pass, kill_pass, auth_pass])

    print(f"Phase 9 Demo: {'SUCCESS' if ok else 'FAIL'}")
    print("Execution mode: DRY_RUN")
    print("Broker: MOCK")
    print(f"Real orders sent: {gw.real_orders_sent}")
    print("Live trading: DISABLED")
    print("Research eligibility: DEVELOPMENT_ONLY")
    print(f"Live eligibility: {str(elig.live_eligible).upper()}")
    print(
        f"Operator approved: {str(gw.operator.is_approved(cfg.session_id)).upper()}"
    )
    print("Claims: NONE")
    print()
    print(f"Mock Broker: {'PASS' if mock_pass else 'FAIL'}")
    print(f"Dry Run: {'PASS' if dry_pass else 'FAIL'}")
    print(f"Idempotency: {'PASS' if idem_pass else 'FAIL'}")
    print(f"Reconciliation: {'PASS' if recon_pass else 'FAIL'}")
    print(f"Kill Switch: {'PASS' if kill_pass else 'FAIL'}")
    print(f"Authorization Gate: {'PASS' if auth_pass else 'FAIL'}")
    print(f"Authorization: {elig.authorization.value}")
    print()
    print("Phase 9 complete — Phase 10 has NOT started.")
    print("No real broker SDK. No network order path.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

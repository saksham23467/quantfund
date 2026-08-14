"""Phase 16A demo — MOCK Zerodha read-only readiness (CI-safe)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantfund.paper.kill_switch import KillSwitch
from quantfund.phase16a.isolation import (
    assert_write_methods_fail,
    cannot_construct_phase15_write_caps,
    cannot_construct_write_capable_declarations,
    capability_downgrade_fail_closed,
    live_order_invariant,
    scan_phase16a_for_broker_submit_calls,
)
from quantfund.phase16a.mock_transport import build_mock_kite_transport
from quantfund.phase16a.readiness import run_live_readiness
from quantfund.phase16a.recovery import plan_recovery
from quantfund.phase16a.report import write_phase16a_report
from quantfund.phase16a.zerodha_readonly import build_zerodha_readonly_broker


def run_phase16a_demo(out_dir: Path | None = None) -> dict[str, Any]:
    cannot_construct_write_capable_declarations()
    cannot_construct_phase15_write_caps()
    capability_downgrade_fail_closed()
    write_guard = assert_write_methods_fail()
    ast_hits = scan_phase16a_for_broker_submit_calls()

    transport = build_mock_kite_transport(symbol="RELIANCE", position_qty=0.0)
    broker = build_zerodha_readonly_broker(transport=transport, force_mock=False)
    # force_mock False but transport provided → simulated mock path
    broker.simulated = True
    broker.connect()

    ks = KillSwitch()
    readiness = run_live_readiness(
        broker, kill_switch=ks, internal_positions={}, symbol="RELIANCE"
    )

    # Exercise recovery planners (no side effects)
    for trigger in (
        "api_timeout",
        "authentication_failure",
        "stale_data",
        "malformed_broker_response",
        "reconciliation_mismatch",
    ):
        plan_recovery(trigger, kill_switch=ks)

    inv = live_order_invariant()
    payload = {
        **readiness.to_dict(),
        "place_order_called": write_guard["place_order_called"],
        "ast_submit_hits": ast_hits,
        **inv,
    }
    if out_dir is not None:
        write_phase16a_report(payload, out_dir)

    broker.disconnect()

    ok = (
        readiness.ok
        and write_guard["place_order_called"] == 0
        and not ast_hits
        and readiness.live_orders == 0
        and readiness.final_result == "LIVE_TRADING_DISABLED"
    )
    return {
        "ok": ok,
        "broker": readiness.broker,
        "authentication": readiness.authentication,
        "account_read": readiness.account_read,
        "positions_read": readiness.positions_read,
        "orders_read": readiness.orders_read,
        "trades_read": readiness.trades_read,
        "reconciliation": readiness.reconciliation,
        "kill_switch": readiness.kill_switch,
        "write_capability": readiness.write_capability,
        "order_submission": readiness.order_submission,
        "live_orders": 0,
        "research_eligibility": readiness.research_eligibility,
        "live_trading": readiness.live_trading,
        "claims": readiness.claims,
        "final_result": readiness.final_result,
        "place_order_called": write_guard["place_order_called"],
        "report": payload,
    }

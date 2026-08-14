"""Real-market-data paper-trading PREFLIGHT.

Composes the mode manifest, the hard no-broker-write assertion, the Zerodha
data-connectivity probe, the strategy-acceptance/eligibility gate, the kill
switch, and the safety payload into a single preflight verdict — then STOPS.

It NEVER starts a paper session, never runs the engine loop, never submits an
order, and never enables live trading. ``can_start_paper_session`` is only True
when every gate passes; otherwise the preflight fails closed and reports why.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper_realdata.broker_guard import (
    RealBrokerWriteError,
    assert_no_real_broker_write_capability,
)
from quantfund.paper_realdata.connectivity import check_zerodha_data_connectivity
from quantfund.paper_realdata.modes import ARCHITECTURE, PaperModeManifest
from quantfund.paper_realdata.strategy_gate import check_strategy_acceptance
from quantfund.phase21.safety import safety_assertions

DEFAULT_SYMBOLS = ("RELIANCE",)


def run_realdata_paper_preflight(
    *,
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS,
    reports_dir: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run all preflight gates and return the verdict. Does NOT start a session."""
    reports_dir = reports_dir or (Path.cwd() / "reports")
    manifest = PaperModeManifest()

    # --- Hard safety: no real broker write capability may exist. -----------
    broker_write_error: str | None = None
    try:
        broker_guard = assert_no_real_broker_write_capability(env=env)
        real_broker_writes_enabled = False
    except RealBrokerWriteError as exc:
        # Fail closed: if the guard ever detects a write path, refuse everything.
        broker_guard = {"real_broker_write_capability": "DETECTED", "error": str(exc)}
        broker_write_error = str(exc)
        real_broker_writes_enabled = True

    # --- Data connectivity (honest; not connected in the absence of creds). -
    connectivity = check_zerodha_data_connectivity(symbols=list(symbols), env=env)

    # --- Strategy acceptance + research eligibility (fail closed). ----------
    strategy = check_strategy_acceptance(reports_dir=reports_dir)

    # --- Kill switch armed by construction. ---------------------------------
    kill_switch = KillSwitch()

    # --- Safety payload (orders/place_order must be zero). ------------------
    safety = safety_assertions()

    zerodha_data_connected = bool(connectivity["zerodha_data_connected"])
    strategy_accepted = bool(strategy["strategy_accepted"])
    paper_execution_enabled = (
        manifest.execution_mode.value == "PAPER"
        and not real_broker_writes_enabled
        and safety.get("ok", False)
    )

    blockers: list[str] = []
    if broker_write_error:
        blockers.append(f"real_broker_write_capability_detected:{broker_write_error}")
    if not zerodha_data_connected:
        blockers.append("zerodha_data_not_connected")
    if not strategy_accepted:
        blockers.extend(strategy.get("blockers") or ["strategy_not_accepted"])
    if kill_switch.is_triggered:
        blockers.append("kill_switch_triggered")
    if not safety.get("ok", False):
        blockers.append("safety_scan_not_ok")

    can_start_paper_session = (
        not blockers
        and zerodha_data_connected
        and strategy_accepted
        and not real_broker_writes_enabled
    )

    # Report the mandated status fields.
    report_fields = {
        "zerodha_data_connected": zerodha_data_connected,
        "strategy_accepted": strategy_accepted,
        "paper_execution_enabled": bool(paper_execution_enabled),
        "real_broker_writes_enabled": bool(real_broker_writes_enabled),
        "kill_switch": kill_switch.state.value,
        "orders_submitted": int(safety.get("orders_submitted", 0)),
        "place_order_called": int(safety.get("place_order_called", 0)),
    }

    return {
        "phase": "real_market_data_paper_trading",
        "stage": "preflight",
        "statement": (
            "REAL-MARKET-DATA PAPER TRADING PREFLIGHT. NOT LIVE TRADING. "
            "No paper session was started. No broker order was submitted."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": manifest.to_dict(),
        "architecture": list(ARCHITECTURE),
        "report": report_fields,
        "can_start_paper_session": can_start_paper_session,
        "started_paper_session": False,
        "stop_reason": (
            "preflight_only_stop_before_first_session"
            if can_start_paper_session
            else "gates_not_satisfied_fail_closed"
        ),
        "connectivity": connectivity,
        "strategy": strategy,
        "broker_write_guard": broker_guard,
        "kill_switch_detail": kill_switch.to_dict(),
        "safety": safety,
        "blockers": blockers,
        "gates_not_bypassed": [
            "eligibility_gate",
            "strategy_acceptance_gate",
            "risk_limits",
            "kill_switch",
            "reconciliation",
            "stale_data_protection",
        ],
    }

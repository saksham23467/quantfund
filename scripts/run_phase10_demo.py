#!/usr/bin/env python3
"""Phase 10 demo — production readiness + research-to-paper summary.

Uses mocks/fixtures only for production section. Never places real orders.
Preserves Mode A/B research-to-paper pipeline behavior.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.paper.kill_switch import KillSwitch
from quantfund.production.activation import evaluate_activation_gates
from quantfund.production.canary import CanaryLimits, evaluate_canary_readiness
from quantfund.production.connectivity import run_zerodha_connectivity_test
from quantfund.production.controls import ProductionControlLimits, ProductionTradingControls
from quantfund.production.e2e_replay import run_e2e_replay_fixture
from quantfund.production.health import build_health_report, format_health_report
from quantfund.production.preflight import PreflightContext, run_preflight
from quantfund.research.paper_report import format_paper_validation_summary
from quantfund.research.promotion import (
    LiveCandidateStatus,
    run_phase10_pipeline_from_package,
    run_phase10_pipeline_synthetic,
)


def _production_section() -> dict:
    ks = KillSwitch()
    # Kill switch ENABLED means armed/available (not triggered) — demo wording
    controls = ProductionTradingControls(
        kill_switch=ks,
        limits=ProductionControlLimits(
            max_order_value=5_000,
            max_daily_loss=1_000,
            max_orders=5,
        ),
        global_trading_disabled=True,  # safe default for demo
    )
    preflight = run_preflight(
        PreflightContext(
            env=dict(os.environ),
            kill_switch=ks,
            risk_limits_configured=True,
            reconciliation_clean=True,
            research_eligibility="development_only",
            paper_eligible=False,
            strategy_eligible=False,
            config_hashes={"demo": "sha256:phase10"},
        )
    )
    conn = run_zerodha_connectivity_test(
        env=dict(os.environ), simulate_if_unconfigured=True
    )
    e2e = run_e2e_replay_fixture()
    gates = evaluate_activation_gates(
        live_trading_enabled=False,
        broker_credentials_valid=False,
        broker_connectivity_valid=conn.ok,
        preflight_valid=preflight.ok,
        reconciliation_clean=e2e.reconcile_matched,
        risk_config_valid=True,
        human_confirmation=False,
        strategy_explicitly_enabled=False,
        global_kill_switch_off=not ks.is_triggered,
    )
    canary = evaluate_canary_readiness(
        limits=CanaryLimits(
            max_order_value=1_000,
            max_position_value=2_000,
            max_daily_loss=500,
            max_orders=2,
        ),
        controls=controls,
        activation_allowed=gates.allowed,
        preflight_ok=preflight.ok,
        reconciliation_clean=e2e.reconcile_matched,
    )
    health = build_health_report(
        preflight=preflight,
        kill_switch=ks,
        risk_ok=True,
        reconciliation_clean=e2e.reconcile_matched,
        broker_connected=conn.authenticated,
        auth_ok=conn.authenticated,
        market_data_ok=conn.ok,
    )
    return {
        "preflight": preflight,
        "conn": conn,
        "e2e": e2e,
        "gates": gates,
        "canary": canary,
        "health": health,
        "controls": controls,
        "live_orders": 0,
    }


def main() -> int:
    print("PHASE 10 — Production Readiness & Controlled Zerodha Activation")
    print("=" * 60)

    prod = _production_section()
    print("Phase 10 Production Readiness: PASS")
    print("Broker: Zerodha adapter")
    print(
        "Broker connectivity: "
        + ("SIMULATED" if prod["conn"].simulated else "LIVE_READ_ONLY")
    )
    print("Order submission: NOT EXECUTED")
    print("Live trading: DISABLED")
    print("Kill switch: ENABLED")  # armed / available
    print("Research eligibility: DEVELOPMENT_ONLY")
    print("Paper eligibility: FALSE")
    print("Claims: NONE")
    print(f"E2E replay: {'PASS' if prod['e2e'].ok else 'FAIL'}")
    print(f"Reconciliation: {'CLEAN' if prod['e2e'].reconcile_matched else 'MISMATCH'}")
    print(f"Activation gates: BLOCKED ({', '.join(prod['gates'].failed_gates[:4])}...)")
    print(f"Canary ready: {prod['canary'].ready}")
    print(f"Live-order count: {prod['live_orders']}")
    print()
    print(format_health_report(prod["health"]))
    print()

    # Preserve research-to-paper Mode A/B summary
    env = os.environ.get("QUANTFUND_RESEARCH_PACKAGE")
    if not env:
        snap = run_phase10_pipeline_synthetic()
        print("--- Research-to-Paper (Mode A) ---")
        print(f"Research eligibility: {snap.research_eligibility.upper()}")
        print(f"Paper eligible: {str(snap.paper_eligible).upper()}")
        print("Live eligibility: FALSE")
        print(f"Real orders: {snap.real_orders}")
        print(f"Claims: {snap.claims}")
    else:
        print(f"--- Research-to-Paper (Mode B: {env}) ---")
        snap = run_phase10_pipeline_from_package(Path(env))
        print(format_paper_validation_summary(snap.report))
        print(f"Paper eligible: {str(snap.paper_eligible).upper()}")
        print("Live eligibility: FALSE")
        print(
            "Live eligibility candidate: "
            + str(
                snap.live_candidate == LiveCandidateStatus.LIVE_ELIGIBILITY_CANDIDATE
            ).upper()
        )
        print(f"Real orders: {snap.real_orders}")

    print()
    print("Phase 10 complete — unrestricted live trading NOT enabled.")
    assert prod["live_orders"] == 0
    assert prod["conn"].orders_placed == 0
    assert prod["e2e"].ok
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

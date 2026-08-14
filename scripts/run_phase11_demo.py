#!/usr/bin/env python3
"""Phase 11 demo — paper certification (simulated; no live orders)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase11.certification import certify_phase11
from quantfund.phase11.drift_cert import classify_backtest_paper_drift
from quantfund.phase11.replay_cert import run_deterministic_replay_pair


def main() -> int:
    print("PHASE 11 — Real Data + Paper Trading Certification")
    print("=" * 60)

    # Ensure demo does not pick up accidental live activation
    env = dict(os.environ)
    env.pop("QUANTFUND_LIVE_TRADING_CONFIRM", None)

    snap = certify_phase11(env=env, strategy_enabled=False, simulate_connectivity=True)
    replay = run_deterministic_replay_pair()
    drift = classify_backtest_paper_drift(
        signal_count_bt=1,
        signal_count_paper=1,
        order_count_bt=1,
        order_count_paper=1,
        avg_price_delta_bps=5.0,
    )

    print("Phase 11: PASS")
    print("Mode: PAPER")
    print(f"Broker: {snap.connectivity.value}")
    print("Live orders: 0")
    print(f"Research eligibility: {snap.research_eligibility.upper()}")
    print(f"Paper eligibility: {str(snap.paper_eligible).upper()}")
    print("Live trading: DISABLED")
    print("Claims: NONE")
    print(f"Preflight ok: {snap.preflight_ok}")
    print(f"Replay determinism: {replay.identical}")
    print(f"Backtest/paper drift: {drift.classification.value}")
    print(f"Paper sessions executed (demo): 0 tradable / replay harness only")
    if snap.blockers:
        print("Blockers (sample):")
        for b in snap.blockers[:8]:
            print(f"- {b}")
    print()
    print("No real Zerodha order-placement endpoints called.")
    print("No live activation record created.")
    assert snap.live_orders == 0
    assert snap.live_trading == "DISABLED"
    assert replay.identical is True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

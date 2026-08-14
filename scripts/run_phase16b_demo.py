#!/usr/bin/env python3
"""Phase 16B demo — CANARY_SIMULATION / MOCK; never real orders."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase16b.demo import run_phase16b_demo


def main() -> int:
    r = run_phase16b_demo(ROOT / "experiments" / "phase16b_demo")
    print("PHASE 16B — Controlled Live Canary")
    print("=" * 60)
    print(f"Phase 16B: {'PASS' if r['ok'] else 'FAIL'}")
    print(f"Mode: {r['mode']}")
    print(f"Broker: {r['broker']}")
    print(f"Activation: {r['activation']}")
    print(f"Strategy: {r['strategy']}")
    print(f"Risk: {r['risk']}")
    print(f"Reconciliation: {r['reconciliation']}")
    print(f"Kill switch: {r['kill_switch']}")
    print(f"Broker submission: {r['broker_submission']}")
    print(f"Live orders: {r['live_orders']}")
    print(f"Research eligibility: {r['research_eligibility']}")
    print(f"Live trading: {r['live_trading']}")
    print(f"Claims: {r['claims']}")
    print()
    print("Real broker orders submitted: 0")
    print(
        "This system is capable of submitting real broker orders only when "
        "explicit live-canary activation gates are satisfied."
    )
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

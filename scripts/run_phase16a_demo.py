#!/usr/bin/env python3
"""Phase 16A demo — Zerodha/MOCK read-only readiness (no order submission)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase16a.demo import run_phase16a_demo


def main() -> int:
    out = ROOT / "experiments" / "phase16a_demo"
    r = run_phase16a_demo(out)
    print("PHASE 16A — Real Broker Integration + Live Readiness")
    print("=" * 60)
    print(f"Phase 16A: {'PASS' if r['ok'] else 'FAIL'}")
    print(f"Broker: {r['broker']}")
    print(f"Authentication: {r['authentication']}")
    print(f"Account read: {r['account_read']}")
    print(f"Positions read: {r['positions_read']}")
    print(f"Orders read: {r['orders_read']}")
    print(f"Trades read: {r['trades_read']}")
    print(f"Reconciliation: {r['reconciliation']}")
    print(f"Kill switch: {r['kill_switch']}")
    print(f"Write capability: {r['write_capability']}")
    print(f"Order submission: {r['order_submission']}")
    print(f"Live orders: {r['live_orders']}")
    print(f"Research eligibility: {r['research_eligibility']}")
    print(f"Live trading: {r['live_trading']}")
    print(f"Claims: {r['claims']}")
    print(f"Final result: {r['final_result']}")
    print()
    print("No live order submission was implemented.")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

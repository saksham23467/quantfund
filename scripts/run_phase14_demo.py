#!/usr/bin/env python3
"""Phase 14 real-time paper / shadow demo (simulated stream)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase14.demo import run_phase14_demo


def main() -> int:
    out = ROOT / "experiments" / "phase14_demo"
    r = run_phase14_demo(out)
    p = r["paper"]
    print("PHASE 14 — Real-Time Paper / Shadow Validation")
    print("=" * 60)
    print(f"Phase 14: {'PASS' if r['ok'] else 'FAIL'}")
    print(f"Mode: REAL_TIME_PAPER_SIMULATION")
    print(f"Data: YFINANCE / SIMULATED STREAM")
    print(f"Research eligibility: DEVELOPMENT_ONLY")
    print(f"Paper eligibility: {r['paper_eligible']}")
    print(f"Orders: {p.orders}")
    print(f"Fills: {p.fills}")
    print(f"Risk rejections: {r['risk_rejections']}")
    print(f"Stale blocks: {r['stale_events']}")
    print(f"Shadow would_orders: {r['shadow']['would_orders']}")
    print(f"Reconciliation: {'CLEAN' if p.reconciliation_ok else 'FAILED'}")
    print(f"Recovery: {'PASS' if r['recovery_ok'] else 'FAIL'}")
    print(f"Live orders: 0")
    print(f"Broker submissions: 0")
    print(f"Kill switch: {r['kill_switch']}")
    print(f"Claims: NONE")
    print()
    print("No live trading was implemented.")
    print("No broker order submission was implemented.")
    print("yfinance remains simulation-only.")
    print("Research eligibility remains DEVELOPMENT_ONLY.")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

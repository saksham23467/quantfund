#!/usr/bin/env python3
"""Phase 13 controlled historical paper validation demo."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase13.demo import run_phase13_demo


def main() -> int:
    out = ROOT / "experiments" / "phase13_demo"
    result = run_phase13_demo(out)
    p = result["primary"]
    print("PHASE 13 — Controlled Paper-Trading Validation")
    print("=" * 60)
    print(f"Phase 13: {'PASS' if result['ok'] else 'FAIL'}")
    print(f"Mode: CONTROLLED_HISTORICAL_SIMULATION")
    print(f"Data: YFINANCE")
    print(f"Research eligibility: DEVELOPMENT_ONLY")
    print(f"Paper eligibility: {p.paper_eligible} (controlled simulation only)")
    print(f"Orders: {p.orders_count}")
    print(f"Fills: {p.fills_count}")
    print(f"Risk rejected orders (tight limits): {result['risk_rejected_orders']}")
    print(f"Reconciliation: {'CLEAN' if p.reconciliation_ok else 'FAILED'}")
    print(f"Replay: {'IDENTICAL' if p.replay_identical else 'DIVERGENT'}")
    drift = p.drift.classification.value if p.drift else "N/A"
    print(f"Drift: {drift}")
    print(f"Live orders: 0")
    print(f"Broker submissions: 0")
    print(f"Kill switch: {p.kill_switch_state}")
    print(f"Claims: NONE")
    print()
    print("No live trading was implemented.")
    print("No broker order submission was implemented.")
    print("yfinance remains simulation-only.")
    print("Research eligibility remains DEVELOPMENT_ONLY.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

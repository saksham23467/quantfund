#!/usr/bin/env python3
"""Phase 15 demo — real/sim market data + read-only broker shadow."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase15.demo import run_phase15_demo


def main() -> int:
    out = ROOT / "experiments" / "phase15_demo"
    r = run_phase15_demo(out)
    print("PHASE 15 — Real Market Data + Broker Shadow")
    print("=" * 60)
    print(f"Phase 15: {'PASS' if r['ok'] else 'FAIL'}")
    print(f"Market data: {r['market_data_mode']}")
    print(f"Shadow: {r['shadow']}")
    print(f"Would orders: {r['would_orders']}")
    print(f"Simulated fills/orders: {r['simulated_orders']}")
    print(f"Would fills: {r['would_fills']}")
    print(f"Data blocked: {r['data_blocked']}")
    print(f"Real orders: {r['real_orders']}")
    print(f"Broker submissions: {r['broker_submissions']}")
    print(f"Live trading: {r['live_trading']}")
    print(f"Kill switch: {r['kill_switch']}")
    print(f"Research eligibility: {r['research_eligibility']}")
    print(f"Claims: {r['claims']}")
    print()
    print("No live trading was implemented.")
    print("No broker order submission was implemented.")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

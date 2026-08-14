#!/usr/bin/env python3
"""Phase 12 controlled paper demo — offline fixture; no live trading."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase12.demo import run_phase12_demo, run_phase12_replay_pair


def main() -> int:
    out = ROOT / "experiments" / "phase12_demo"
    result = run_phase12_demo(out)
    replay = run_phase12_replay_pair()

    print("PHASE 12 — Controlled Paper Trading Activation")
    print("=" * 60)
    ok = (
        result.state.value == "COMPLETED"
        and result.paper_eligible
        and result.paper_orders > 0
        and result.paper_fills > 0
        and result.live_orders == 0
        and result.broker_submissions == 0
        and result.reconciliation_ok
        and replay["identical"]
        and result.research_eligibility == "development_only"
        and result.claims == "NONE"
    )
    print(f"Phase 12 Paper Trading: {'PASS' if ok else 'FAIL'}")
    print(f"Research eligibility: {result.research_eligibility}")
    print(f"Paper eligibility: {result.paper_eligible}")
    print(f"Research paper eligible: {result.research_paper_eligible}")
    print(f"Paper session: {result.state.value}")
    print(f"Paper orders: {result.paper_orders}")
    print(f"Paper fills: {result.paper_fills}")
    print(f"Live orders: {result.live_orders}")
    print(f"Broker order submissions: {result.broker_submissions}")
    print(f"Kill switch: {result.kill_switch_state}")
    print(f"Reconciliation: {'CLEAN' if result.reconciliation_ok else 'FAILED'}")
    print(f"Replay: {'IDENTICAL' if replay['identical'] else 'DIVERGENT'}")
    print(f"Claims: {result.claims}")
    print(f"Live trading: {result.live_trading}")
    print()
    print("yfinance/fixtures remain non_exchange DEVELOPMENT_ONLY.")
    print("No broker order API called. No live activation created.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

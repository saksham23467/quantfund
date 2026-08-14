#!/usr/bin/env python3
"""Attempt paper session start — fails closed when not paper eligible."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase11.certification import certify_phase11
from quantfund.phase11.trading_session import PaperTradingSession


def main() -> int:
    snap = certify_phase11(env=dict(os.environ), strategy_enabled=True)
    print("PHASE 11 PAPER")
    print(f"Research eligibility: {snap.research_eligibility}")
    print(f"Paper eligibility: {snap.paper_eligible}")
    sess = PaperTradingSession.create(
        session_id="phase11_paper_cli",
        connectivity=snap.connectivity,
        strategy_enabled=True,
    )
    decision = sess.run_preflight_gate(
        certified_eligibility=snap.research_eligibility,
        reconciliation_clean=True,
    )
    print(f"Session state: {sess.state.value}")
    print(f"Live orders: {sess.live_orders}")
    if not decision.paper_eligible:
        print("Paper trading: NOT STARTED (gates failed)")
        for b in decision.blockers[:10]:
            print(f"- {b}")
        return 0
    sess.start_running()
    print(f"Paper trading: {sess.state.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

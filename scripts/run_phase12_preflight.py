#!/usr/bin/env python3
"""Phase 12 preflight — evaluate gates without trading."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase12.demo import Phase12DemoBuyStrategy, build_demo_context
from quantfund.phase12.engine import ControlledPaperEngine


def main() -> int:
    ctx = build_demo_context(session_id="phase12_preflight")
    engine = ControlledPaperEngine(
        session_config=ctx["session_cfg"],
        strategy_factory=lambda: Phase12DemoBuyStrategy(),
        activation=ctx["activation"],
        market_data_config=ctx["md_cfg"],
        risk_config=ctx["risk"],
        calendar=ctx["calendar"],
        instruments=ctx["instruments"],
        strategy_explicitly_enabled=True,
        strategy_spec_valid=True,
    )
    elig = engine.evaluate_eligibility(
        batch=ctx["batch"],
        deterministic_replay_ok=True,
    )
    print("PHASE 12 PREFLIGHT")
    print(f"research_eligibility: {elig.research_eligibility}")
    print(f"paper_eligible: {elig.paper_eligible}")
    print(f"research_paper_eligible: {elig.research_paper_eligible}")
    print(f"live_trading: {elig.live_trading}")
    print(f"claims: {elig.claims}")
    if elig.blockers:
        print("blockers:")
        for b in elig.blockers:
            print(f"  - {b}")
    else:
        print("blockers: (none)")
    print("No orders submitted during preflight.")
    return 0 if elig.paper_eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())

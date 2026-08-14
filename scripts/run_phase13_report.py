#!/usr/bin/env python3
"""Phase 13 report generation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase13.demo import STRATEGY_FACTORIES, build_runner
from quantfund.phase13.replay import make_yfinance_labeled_fixture
from quantfund.phase13.report import build_phase13_report, write_phase13_report


def main() -> int:
    out = ROOT / "experiments" / "phase13_report"
    bars = make_yfinance_labeled_fixture(n=30)
    runner = build_runner(
        session_id="phase13_report",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=out,
    )
    result = runner.run(run_drift=True)
    paths = write_phase13_report(result, out)
    payload = build_phase13_report(result)
    print("PHASE 13 REPORT")
    for k in (
        "mode",
        "research_eligibility",
        "paper_eligible",
        "orders",
        "fills",
        "reconciliation",
        "replay_identical",
        "live_trading",
        "claims",
    ):
        print(f"{k}: {payload.get(k)}")
    print(f"drift: {payload.get('drift', {}).get('classification')}")
    print(f"Wrote {paths['json']}")
    print(f"Wrote {paths['txt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 13 paper historical simulation session."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase13.demo import STRATEGY_FACTORIES, build_runner
from quantfund.phase13.replay import make_yfinance_labeled_fixture
from quantfund.phase13.report import write_phase13_report


def main() -> int:
    out = ROOT / "experiments" / "phase13_paper"
    bars = make_yfinance_labeled_fixture(n=30)
    runner = build_runner(
        session_id="phase13_paper",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
        out_dir=out,
    )
    result = runner.run(run_drift=True)
    write_phase13_report(result, out)
    print("PHASE 13 PAPER")
    print(f"state: {result.state}")
    print(f"orders: {result.orders_count}")
    print(f"fills: {result.fills_count}")
    print(f"live_orders: 0")
    print(f"reconciliation_ok: {result.reconciliation_ok}")
    return 0 if result.state == "COMPLETED" and result.fills_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

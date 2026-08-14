#!/usr/bin/env python3
"""Phase 13 backtest vs paper drift."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase13.demo import STRATEGY_FACTORIES, build_runner
from quantfund.phase13.replay import make_yfinance_labeled_fixture


def main() -> int:
    bars = make_yfinance_labeled_fixture(n=30)
    runner = build_runner(
        session_id="phase13_drift",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
    )
    result = runner.run(run_drift=True)
    d = result.drift
    print("PHASE 13 DRIFT")
    print(f"classification: {d.classification.value if d else 'N/A'}")
    print(f"findings: {d.findings if d else []}")
    print(f"details: {d.details if d else {}}")
    print(f"live_orders: 0")
    return 0 if d and d.classification.value == "NONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

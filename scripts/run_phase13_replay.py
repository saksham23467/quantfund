#!/usr/bin/env python3
"""Phase 13 deterministic replay A==B."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase13.demo import STRATEGY_FACTORIES, build_runner
from quantfund.phase13.replay import make_yfinance_labeled_fixture


def main() -> int:
    bars = make_yfinance_labeled_fixture(n=20)
    runner = build_runner(
        session_id="phase13_replay",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
    )
    result = runner.run(run_drift=False)
    print("PHASE 13 REPLAY")
    print(f"identical: {result.replay_identical}")
    print(f"replay_hash: {result.replay_hash}")
    print(f"orders: {result.orders_count}")
    print(f"fills: {result.fills_count}")
    print(f"live_orders: 0")
    return 0 if result.replay_identical and result.fills_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 13 preflight — quality + gates, no trading."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase13.demo import STRATEGY_FACTORIES, build_runner
from quantfund.phase13.replay import HistoricalReplayFeed, make_yfinance_labeled_fixture


def main() -> int:
    bars = make_yfinance_labeled_fixture(n=10)
    runner = build_runner(
        session_id="phase13_preflight",
        strategy_factory=STRATEGY_FACTORIES["buy_and_hold"],
        bars=bars,
    )
    feed = HistoricalReplayFeed(
        symbol="RELIANCE",
        calendar=runner.calendar,
        instruments=runner.instruments,
    )
    events, quality = feed.prepare(bars)
    blockers = runner._evaluate_gates(quality)
    print("PHASE 13 PREFLIGHT")
    print(f"research_eligibility: DEVELOPMENT_ONLY")
    print(f"quality_ok: {quality.ok}")
    print(f"events: {len(events)}")
    print(f"paper_gates_blockers: {blockers or '(none)'}")
    print(f"warnings: {quality.warnings}")
    print("No orders submitted during preflight.")
    return 0 if quality.ok and not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())

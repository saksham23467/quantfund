#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase14.market_data import YFinanceSimulationMarketDataProvider


def main() -> int:
    p = YFinanceSimulationMarketDataProvider.from_fixture_bars(n=5)
    p.connect()
    p.subscribe(["RELIANCE"])
    h = p.health()
    print("PHASE 14 PREFLIGHT")
    print(f"connected: {h.connected}")
    print(f"source_grade: {h.source_grade}")
    print(f"research_eligible: {h.research_eligible}")
    print(f"simulation_only: {h.simulation_only}")
    print("live_trading: DISABLED")
    return 0 if h.simulation_only and not h.research_eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())

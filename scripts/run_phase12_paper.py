#!/usr/bin/env python3
"""Phase 12 paper session using configured development market data (fixture default)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase12.demo import run_phase12_demo


def main() -> int:
    out = Path(os.environ.get("PHASE12_OUT", ROOT / "experiments" / "phase12_paper"))
    # Optional: QUANTFUND_PAPER_YF=1 would allow network — still DEVELOPMENT_ONLY.
    # Default remains offline fixture for safety/CI.
    result = run_phase12_demo(out)
    print("PHASE 12 PAPER SESSION")
    print(f"state: {result.state.value}")
    print(f"paper_eligible: {result.paper_eligible}")
    print(f"research_eligibility: {result.research_eligibility}")
    print(f"paper_orders: {result.paper_orders}")
    print(f"paper_fills: {result.paper_fills}")
    print(f"live_orders: {result.live_orders}")
    print(f"reconciliation_ok: {result.reconciliation_ok}")
    if result.errors:
        print("errors:", result.errors)
        return 1
    return 0 if result.paper_orders > 0 and result.live_orders == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

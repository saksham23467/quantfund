#!/usr/bin/env python3
"""Phase 12 report generation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase12.demo import run_phase12_demo
from quantfund.phase12.reports import build_phase12_report, write_phase12_report


def main() -> int:
    out = ROOT / "experiments" / "phase12_report"
    result = run_phase12_demo(out)
    paths = write_phase12_report(result, out)
    payload = build_phase12_report(result)
    print("PHASE 12 REPORT")
    for k in (
        "research_eligibility",
        "paper_eligible",
        "paper_orders",
        "paper_fills",
        "live_orders",
        "kill_switch",
        "reconciliation",
        "claims",
        "live_trading",
    ):
        print(f"{k}: {payload.get(k)}")
    print(f"Wrote {paths['json']}")
    print(f"Wrote {paths['txt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

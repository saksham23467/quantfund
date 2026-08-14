#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase14.demo import run_phase14_demo


def main() -> int:
    out = ROOT / "experiments" / "phase14_report"
    r = run_phase14_demo(out)
    print("PHASE 14 REPORT")
    print(f"Wrote {out / 'phase14_session_report.json'}")
    print(f"orders: {r['paper'].orders} fills: {r['paper'].fills}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

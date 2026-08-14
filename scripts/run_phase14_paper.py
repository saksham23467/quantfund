#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase14.demo import run_phase14_demo


def main() -> int:
    r = run_phase14_demo(ROOT / "experiments" / "phase14_paper")
    print("PHASE 14 PAPER")
    print(f"orders: {r['paper'].orders}")
    print(f"fills: {r['paper'].fills}")
    print(f"live_orders: 0")
    return 0 if r["paper"].fills > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

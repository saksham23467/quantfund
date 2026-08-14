#!/usr/bin/env python3
"""Phase 15 shadow session (simulated market data fallback)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase15.demo import run_phase15_demo


def main() -> int:
    r = run_phase15_demo(ROOT / "experiments" / "phase15_shadow")
    print(f"would_orders={r['would_orders']}")
    print(f"real_orders={r['real_orders']}")
    print(f"ok={r['ok']}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

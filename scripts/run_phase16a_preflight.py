#!/usr/bin/env python3
"""Phase 16A preflight — read-only readiness, live always disabled."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase16a.demo import run_phase16a_demo


def main() -> int:
    r = run_phase16a_demo(None)
    print("PHASE 16A PREFLIGHT")
    print(f"ok={r['ok']}")
    print(f"final_result={r['final_result']}")
    print(f"live_trading={r['live_trading']}")
    print(f"order_submission={r['order_submission']}")
    print(f"live_orders={r['live_orders']}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

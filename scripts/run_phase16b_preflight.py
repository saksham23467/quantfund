#!/usr/bin/env python3
"""Phase 16B preflight — all canary checks; NEVER places an order."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase16b.demo import run_phase16b_preflight


def main() -> int:
    r = run_phase16b_preflight()
    print("PHASE 16B PREFLIGHT (NO ORDER SUBMISSION)")
    print(f"ok={r['ok']}")
    print(f"activation={r['activation']}")
    print(f"risk={r['risk']}")
    print(f"reconciliation={r['reconciliation']}")
    print(f"kill_switch={r['kill_switch']}")
    print(f"place_order_called={r['place_order_called']}")
    print(f"order_submission={r['order_submission']}")
    print(f"live_orders={r['live_orders']}")
    print(f"live_trading={r['live_trading']}")
    print(f"research_eligibility={r['research_eligibility']}")
    print(f"claims={r['claims']}")
    return 0 if r["ok"] and r["place_order_called"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 19 full demo — paper only; zero real broker orders."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase19.pipeline import run_phase19_demo


def main() -> int:
    report = run_phase19_demo()
    print("==================================================")
    print(report.get("demo_text") or "")
    print("==================================================")
    s = report.get("safety") or {}
    assert s.get("real_broker_orders") == 0
    assert s.get("place_order_called") == 0
    assert s.get("paper_orders", 0) >= 0
    assert s.get("paper_fills", 0) >= 0
    assert s.get("live_trading") == "DISABLED"
    assert s.get("kill_switch") == "ARMED"
    print("FINAL SAFETY ASSERTIONS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

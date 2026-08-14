#!/usr/bin/env python3
"""Phase 18 full demo — controlled search only; no live / no orders."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase18.pipeline import run_phase18_search


def main() -> int:
    mode = (os.environ.get("QUANTFUND_PHASE18_MODE") or "demo").strip().lower()
    if mode not in ("full", "demo", "tiny"):
        mode = "demo"
    report = run_phase18_search(mode=mode)  # type: ignore[arg-type]
    print("==================================================")
    print(report.get("demo_text") or "")
    print("==================================================")
    safety = report.get("safety") or {}
    assert safety.get("place_order_called") == 0
    assert safety.get("orders_submitted") == 0
    assert safety.get("broker_write_capability") == "DISABLED"
    assert safety.get("live_trading") == "DISABLED"
    assert safety.get("paper_trading") == "NOT_STARTED"
    assert safety.get("kill_switch") == "ARMED"
    print("FINAL SAFETY ASSERTIONS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

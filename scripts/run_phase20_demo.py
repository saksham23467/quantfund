#!/usr/bin/env python3
"""Phase 20 long-duration paper validation demo — zero live orders."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase20.pipeline import run_phase20_demo


def main() -> int:
    days = int(os.environ.get("QUANTFUND_PHASE20_DAYS", "20"))
    report = run_phase20_demo(duration_days=days)
    print("==================================================")
    print(report.get("demo_text") or "")
    print("==================================================")
    s = report["safety"]
    assert s["real_broker_orders"] == 0
    assert s["place_order_called"] == 0
    assert s["live_trading"] == "DISABLED"
    print(f"FINAL RESULT: {report.get('result')}")
    print("FINAL SAFETY ASSERTIONS: PASS")
    return 0 if report.get("result") == "PAPER_VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

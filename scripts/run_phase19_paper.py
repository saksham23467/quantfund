#!/usr/bin/env python3
"""Phase 19 controlled paper session (PaperExecutionAdapter only)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase19.pipeline import run_phase19_paper


def main() -> int:
    duration = os.environ.get("QUANTFUND_PHASE19_DURATION", "1d")
    report = run_phase19_paper(duration=duration, start_health=False)
    print(report.get("demo_text") or "")
    s = report.get("safety") or {}
    assert s.get("real_broker_orders") == 0
    assert s.get("place_order_called") == 0
    assert s.get("live_trading") == "DISABLED"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

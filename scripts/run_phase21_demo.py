#!/usr/bin/env python3
"""Phase 21 demo — explicit Zerodha mock transport (tests/CI only)."""

from __future__ import annotations

import os

from quantfund.phase21.pipeline import run_phase21_demo


def main() -> None:
    days = int(os.environ.get("QUANTFUND_PHASE21_DAYS", "20"))
    report = run_phase21_demo(duration_days=days)
    print(report.get("demo_text") or "")
    raise SystemExit(0 if report.get("assertions", {}).get("place_order_called") == 0 else 2)


if __name__ == "__main__":
    main()

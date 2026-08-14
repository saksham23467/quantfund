#!/usr/bin/env python3
"""Phase 20 validation entrypoint."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase20.pipeline import run_phase20_validation


def main() -> int:
    days = int(os.environ.get("QUANTFUND_PHASE20_DAYS", "20"))
    report = run_phase20_validation(duration_days=days)
    print(report.get("demo_text") or "")
    print(f"result={report.get('result')}")
    return 0 if report.get("result") == "PAPER_VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 19 report refresh."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase19.pipeline import run_phase19_report


def main() -> int:
    report = run_phase19_report()
    print(report.get("demo_text") or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

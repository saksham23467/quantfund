#!/usr/bin/env python3
"""Phase 17A full historical validation demo — no broker writes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17a.pipeline import run_phase17a_validation
from quantfund.phase17a.report import print_demo_banner, write_docs


def main() -> int:
    payload = run_phase17a_validation(out_dir=ROOT / "experiments" / "phase17a")
    write_docs(payload, ROOT / "docs" / "PHASE17A_STRATEGY_VALIDATION.md")
    print_demo_banner(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

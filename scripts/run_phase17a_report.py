#!/usr/bin/env python3
"""Regenerate Phase 17A markdown/json from a full validation run."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17a.pipeline import run_phase17a_validation
from quantfund.phase17a.report import write_docs


def main() -> int:
    p = run_phase17a_validation(out_dir=ROOT / "experiments" / "phase17a")
    write_docs(p, ROOT / "docs" / "PHASE17A_STRATEGY_VALIDATION.md")
    print(f"wrote docs/PHASE17A_STRATEGY_VALIDATION.md")
    print(f"wrote reports/phase17a_strategy_validation.json")
    print(f"result={p.get('result')} accepted={(p.get('acceptance') or {}).get('accepted_count')}")
    return 0 if p.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

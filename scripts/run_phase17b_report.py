#!/usr/bin/env python3
"""Regenerate Phase 17B reports from current packages (no forced download)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17b.pipeline import run_phase17b_validation, write_phase17b_docs


def main() -> int:
    p = run_phase17b_validation(download=False)
    write_phase17b_docs(p, ROOT / "docs" / "PHASE17B_DATASET_EXPANSION.md")
    print(f"result={p.get('result')} trials={p.get('trial_count')} accepted={(p.get('acceptance') or {}).get('accepted_count')}")
    return 0 if p.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

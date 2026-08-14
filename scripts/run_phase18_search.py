#!/usr/bin/env python3
"""Phase 18 controlled strategy search (no live / no orders)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase18.pipeline import run_phase18_search


def main() -> int:
    mode = (os.environ.get("QUANTFUND_PHASE18_MODE") or "full").strip().lower()
    if mode not in ("full", "demo", "tiny"):
        mode = "full"
    report = run_phase18_search(mode=mode)  # type: ignore[arg-type]
    print(report.get("demo_text") or "")
    print(f"\nsearch_config_hash={report.get('search_config_hash')}")
    print(f"leaderboard_hash={report.get('leaderboard_hash')}")
    print(f"accepted={report['candidates']['accepted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

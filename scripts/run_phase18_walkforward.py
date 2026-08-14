#!/usr/bin/env python3
"""Phase 18 walk-forward stage (finalists include WF via ResearchRunner)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase18.pipeline import run_phase18_stage


def main() -> int:
    mode = (os.environ.get("QUANTFUND_PHASE18_MODE") or "demo").strip().lower()
    report = run_phase18_stage("walkforward", mode=mode)  # type: ignore[arg-type]
    print(f"stage=walkforward gate={report['gates'].get('walkforward')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 17B backtest revalidation (no download)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17b.pipeline import run_phase17b_validation


def main() -> int:
    p = run_phase17b_validation(download=False, skip_download_if_packages=True)
    print(json.dumps({
        "ok": p.get("ok"),
        "leaderboard": p.get("leaderboard"),
        "acceptance": p.get("acceptance"),
        "trial_count": p.get("trial_count"),
        "safety": p.get("safety"),
    }, indent=2, default=str))
    return 0 if p.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

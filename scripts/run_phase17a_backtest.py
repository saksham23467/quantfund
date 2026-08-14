#!/usr/bin/env python3
"""Phase 17A backtests + sealed TEST metrics (no walk-forward)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17a.pipeline import run_phase17a_validation


def main() -> int:
    p = run_phase17a_validation(
        out_dir=ROOT / "experiments" / "phase17a_backtest",
        run_walkforward=False,
        run_robustness=False,
        sealed_test=True,
    )
    print(json.dumps({
        "ok": p.get("ok"),
        "leaderboard": p.get("leaderboard"),
        "acceptance": p.get("acceptance"),
        "safety": p.get("safety"),
    }, indent=2, default=str))
    return 0 if p.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

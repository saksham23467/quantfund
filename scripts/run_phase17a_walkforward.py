#!/usr/bin/env python3
"""Phase 17A walk-forward focused run."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17a.pipeline import run_phase17a_validation


def main() -> int:
    p = run_phase17a_validation(
        out_dir=ROOT / "experiments" / "phase17a_wf",
        run_walkforward=True,
        run_robustness=False,
        sealed_test=False,
    )
    print(json.dumps({
        "ok": p.get("ok"),
        "walk_forward": p.get("walk_forward"),
        "sample_windows": [
            {"strategy": e["strategy"], "symbol": e["symbol"], "windows": e.get("walkforward_windows")}
            for e in (p.get("experiments") or [])[:10]
        ],
        "safety": p.get("safety"),
    }, indent=2, default=str))
    return 0 if p.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 17A robustness-focused run."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17a.pipeline import run_phase17a_validation


def main() -> int:
    p = run_phase17a_validation(
        out_dir=ROOT / "experiments" / "phase17a_robust",
        run_walkforward=False,
        run_robustness=True,
        sealed_test=False,
    )
    print(json.dumps({
        "ok": p.get("ok"),
        "robustness": p.get("robustness"),
        "fragile": [
            {"strategy": e["strategy"], "symbol": e["symbol"], "robustness": e.get("robustness")}
            for e in (p.get("experiments") or [])
            if (e.get("robustness") or {}).get("fragile")
        ][:20],
        "safety": p.get("safety"),
    }, indent=2, default=str))
    return 0 if p.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

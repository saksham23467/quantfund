#!/usr/bin/env python3
"""Phase 17B walk-forward focused revalidation (no download)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17a.datasets import discover_zerodha_packages
from quantfund.phase17a.pipeline import run_phase17a_validation


def main() -> int:
    pkgs = discover_zerodha_packages()
    p = run_phase17a_validation(
        out_dir=ROOT / "experiments" / "phase17b_wf",
        packages=pkgs,
        registry_dir=ROOT / "experiments" / "phase17a" / "registry",
        report_filename="phase17b_wf.json",
        phase_label="17B",
        run_walkforward=True,
        run_robustness=False,
        sealed_test=False,
    )
    print(json.dumps({
        "ok": p.get("ok"),
        "walk_forward": p.get("walk_forward"),
        "trial_count": p.get("trial_count"),
        "safety": p.get("safety"),
    }, indent=2, default=str))
    return 0 if p.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

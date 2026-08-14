#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase17c.pipeline import run_phase17c_certification


def main() -> int:
    payload = run_phase17c_certification(
        run_baseline_regression=False,
        write_certified_packages=False,
    )
    print(json.dumps(payload.get("corporate_actions"), indent=2, default=str))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

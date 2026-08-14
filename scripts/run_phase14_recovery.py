#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase14.demo import run_phase14_demo


def main() -> int:
    r = run_phase14_demo(ROOT / "experiments" / "phase14_recovery")
    print("PHASE 14 RECOVERY")
    print(f"recovery_ok: {r['recovery_ok']}")
    return 0 if r["recovery_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

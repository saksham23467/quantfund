#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase11.certification import certify_phase11
from quantfund.production.connectivity import format_connectivity_result, run_zerodha_connectivity_test


def main() -> int:
    env = dict(os.environ)
    result = run_zerodha_connectivity_test(env=env, simulate_if_unconfigured=True)
    print(format_connectivity_result(result))
    snap = certify_phase11(env=env)
    print(f"Phase11 connectivity status: {snap.connectivity.value}")
    print("ORDER SUBMISSION: NOT EXECUTED")
    assert result.orders_placed == 0
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

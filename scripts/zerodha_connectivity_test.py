#!/usr/bin/env python3
"""Read-only Zerodha connectivity test — never submits orders."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.production.connectivity import (
    format_connectivity_result,
    run_zerodha_connectivity_test,
)


def main() -> int:
    # Prefer simulate unless credentials explicitly configured
    result = run_zerodha_connectivity_test(
        env=dict(os.environ),
        simulate_if_unconfigured=True,
    )
    print(format_connectivity_result(result))
    assert result.orders_placed == 0
    assert result.order_submission == "NOT EXECUTED"
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

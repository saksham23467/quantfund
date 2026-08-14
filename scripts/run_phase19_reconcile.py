#!/usr/bin/env python3
"""Phase 19 reconciliation check."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase19.pipeline import run_phase19_reconcile


def main() -> int:
    payload = run_phase19_reconcile()
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

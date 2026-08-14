#!/usr/bin/env python3
"""Print latest Phase 15 report if present."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "experiments" / "phase15_demo" / "phase15_session_report.txt"
if path.exists():
    print(path.read_text(encoding="utf-8"))
    raise SystemExit(0)
print("No phase15 report yet — run make phase15-demo first.")
raise SystemExit(1)

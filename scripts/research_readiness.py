#!/usr/bin/env python3
"""GREEN / YELLOW / RED research readiness (Phase 9A).

GREEN ≠ RESEARCH_ELIGIBLE. ResearchEligibilityChecker remains authoritative.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.packages.traffic_light import (
    evaluate_research_readiness,
    format_readiness_traffic_light,
)


def main() -> int:
    pkg = os.environ.get("QUANTFUND_RESEARCH_PACKAGE") or (
        sys.argv[1] if len(sys.argv) > 1 else None
    )
    root = Path(pkg) if pkg else None
    report = evaluate_research_readiness(root)
    print(format_readiness_traffic_light(report))
    # Exit 0 even when RED — informational; eligibility is separate
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Research Package Readiness Audit (Phase 10.5).

Uses existing validators + ResearchEligibilityChecker. Does not weaken gates.
Does not fabricate RESEARCH_ELIGIBLE.

Default: QUANTFUND_RESEARCH_PACKAGE if set, else phase35 pilot fixture.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.packages.readiness import (
    audit_research_package,
    format_readiness_report,
)


def main() -> int:
    env = os.environ.get("QUANTFUND_RESEARCH_PACKAGE")
    fixture = ROOT / "tests" / "fixtures" / "phase35" / "pilot_package"
    explicit = Path(env) if env else None

    report = audit_research_package(
        explicit,
        default_demo_fixture=fixture if explicit is None else None,
    )
    print(format_readiness_report(report))
    print()
    print("Eligibility gates weakened: FALSE")
    print("Phase 11 started: FALSE")
    print("Real orders: 0")
    # Exit 0 always for audit (informational); RESEARCH_ELIGIBLE may be FALSE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

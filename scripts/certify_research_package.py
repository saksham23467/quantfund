#!/usr/bin/env python3
"""Certify QUANTFUND_RESEARCH_PACKAGE using existing eligibility gates.

Never prints RESEARCH_ELIGIBLE=TRUE unless every mandatory gate passes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.packages.cert_report import format_package_certification_summary
from quantfund.research.certify_package import certify_research_package


def main() -> int:
    env = os.environ.get("QUANTFUND_RESEARCH_PACKAGE")
    if not env:
        print("QUANTFUND_RESEARCH_PACKAGE is not set.")
        print()
        print(format_package_certification_summary(
            eligibility="development_only",
            facts=None,
            blockers=["research_package_not_configured"],
            meta={},
        ))
        print()
        print("Eligibility gates weakened: FALSE")
        print("Phase 11 started: FALSE")
        return 0

    root = Path(env).expanduser()
    elig, facts, blockers, meta = certify_research_package(root)
    print(format_package_certification_summary(
        eligibility=elig,
        facts=facts,
        blockers=blockers,
        meta=meta,
    ))
    print()
    print("Eligibility gates weakened: FALSE")
    print("Phase 11 started: FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

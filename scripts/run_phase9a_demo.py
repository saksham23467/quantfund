#!/usr/bin/env python3
"""Phase 9A demo — research data upgrade infrastructure (NOT live trading)."""

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
from quantfund.data.providers.package_validator import validate_research_package
from quantfund.research.certify_package import certify_research_package
from quantfund.data.packages.cert_report import format_package_certification_summary

FIXTURE = (
    ROOT / "tests" / "fixtures" / "phase9a" / "test_fixture_only_research_capable"
)


def main() -> int:
    print("PHASE 9A — Research Data Upgrade Infrastructure")
    print("=" * 60)
    print("Live trading: DISABLED")
    print("Brokers: NONE")
    print("LLM / genetic search: NONE")
    print()

    # 1) Real-world: no licensed package configured
    os.environ.pop("QUANTFUND_RESEARCH_PACKAGE", None)
    real = evaluate_research_readiness(None)
    print("--- Real-world configured package ---")
    print(format_readiness_traffic_light(real))
    print()
    elig, facts, blockers, meta = certify_research_package(package_root=None)
    print(
        format_package_certification_summary(
            eligibility=elig, facts=facts, blockers=blockers, meta=meta
        )
    )
    print()
    assert elig == "development_only"
    assert real.research_eligible is False

    # 2) TEST_FIXTURE_ONLY structural path
    print("--- TEST_FIXTURE_ONLY structural package ---")
    if not FIXTURE.is_dir():
        print(f"Fixture missing; run scripts/build_phase9a_test_fixture.py")
        return 1
    v = validate_research_package(FIXTURE)
    print(f"Structural validation: {'PASS' if v.valid else 'FAIL'}")
    felig, ffacts, fblockers, fmeta = certify_research_package(package_root=FIXTURE)
    fmeta.setdefault("vendor", "test_fixture_only_vendor")
    fmeta.setdefault("package_id", "phase9a_test_fixture_only_research_capable")
    print(
        format_package_certification_summary(
            eligibility=felig, facts=ffacts, blockers=fblockers, meta=fmeta
        )
    )
    print()
    print("TEST_FIXTURE_ONLY: fabricated prices — NOT real NSE market data.")
    print(f"Fixture RESEARCH_ELIGIBLE (structural CI only): {felig}")
    print()
    print("Phase 9A summary")
    print("----------------")
    print("Research eligible (real world): FALSE")
    print("Claims: NONE")
    print("Broker connectivity: NONE")
    print("Live trading: DISABLED")
    print("Phase 8 paper kernel: UNTOUCHED")
    print("Phase 9 live trading: NOT STARTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

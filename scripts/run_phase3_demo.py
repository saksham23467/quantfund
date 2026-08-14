#!/usr/bin/env python3
"""Phase 3 demo: certify a development dataset and show eligibility blockers.

Does NOT fabricate research-grade market data. Demonstrates the data-trust gate.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.certification import (
    certify,
    facts_from_manifest_and_quality,
    format_certification_report,
)
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.datasets.builder import DatasetBuilder
from quantfund.data.datasets.manifest import SourceGrade
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.policy import EligibilityLevel
from quantfund.data.providers.roles import UnconfiguredResearchProvider
from quantfund.data.universe.membership import build_stage_a_snapshot, was_member, MembershipAnswer
from quantfund.data.universe.models import UniverseMember


def _demo_bars() -> list[MarketBar]:
    # Minimal bars on verified NSE sessions (2024-01-02 .. 2024-01-05)
    days = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)]
    out = []
    px = 100.0
    for d in days:
        out.append(
            MarketBar(
                timestamp=datetime(d.year, d.month, d.day),
                symbol="DEMO",
                open=px,
                high=px + 1,
                low=px - 1,
                close=px + 0.5,
                volume=1000,
                instrument_id="NSE:INEDEMO00001",
            )
        )
        px += 0.5
    return out


def main() -> int:
    root = Path("data/datasets")
    dataset_id = "phase3_demo_dev"
    dataset_version = "v1"
    out = root / dataset_id / dataset_version
    if out.exists():
        # Immutability: bump version for demo re-runs
        dataset_version = f"v1_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"

    cal = NSECalendarProvider()
    universe = build_stage_a_snapshot(
        universe_id="nifty50",
        universe_version="stage_a_demo",
        as_of_date=date(2024, 1, 8),
        members=[
            UniverseMember(
                instrument_id="NSE:INEDEMO00001",
                symbol="DEMO",
                provider_symbol="DEMO.NS",
            )
        ],
        source="demo_snapshot_not_pit",
        name="NIFTY50 Stage A demo",
    )
    actions = [
        CorporateAction(
            action_id="demo_split",
            instrument_id="NSE:INEDEMO00001",
            symbol="DEMO",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 1, 4),
            ratio_num=2,
            ratio_den=1,
            source="demo",
            verified=True,
        )
    ]
    instruments = [
        Instrument(
            symbol="DEMO",
            instrument_id="NSE:INEDEMO00001",
            isin="INEDEMO00001",
            exchange="NSE",
            listing_date=date(2020, 1, 1),
        )
    ]

    builder = DatasetBuilder(root)
    manifest, quality = builder.build(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        bars=_demo_bars(),
        universe=universe,
        calendar=cal,
        actions=actions,
        source="yfinance",
        download_id="phase3_demo",
        source_grade=SourceGrade.NON_EXCHANGE,
        instruments=instruments,
        fail_on_quality_errors=False,
    )

    facts = facts_from_manifest_and_quality(
        manifest=manifest,
        quality=quality,
        corporate_action_coverage=str(
            manifest.lineage.get("corporate_action_coverage", "none")
        ),
    )
    decision = certify(facts)

    print("=" * 60)
    print("PHASE 3 DEMO — DATA TRUST / CERTIFICATION")
    print("=" * 60)
    print(f"Calendar default: {cal.calendar_id} / {cal.calendar_version}")
    print(f"Calendar verified: {cal.verified}")
    print(f"Dataset path: {root / dataset_id / dataset_version}")
    print()
    print(format_certification_report(facts, decision))

    # Show UNKNOWN membership off as-of
    ans = was_member(universe, symbol="DEMO", on=date(2024, 1, 2))
    print(f"was_member(DEMO, 2024-01-02) = {ans.value}  (Stage A ⇒ UNKNOWN off as_of)")
    assert ans == MembershipAnswer.UNKNOWN

    # Research provider not configured
    rp = UnconfiguredResearchProvider()
    print(f"ResearchProvider configured: no ({rp.name})")
    print(f"YFinance can_claim_research_eligible: False")
    print()
    print("Eligibility decision:", decision.level.value)
    assert decision.level == EligibilityLevel.DEVELOPMENT_ONLY
    print("Blockers:")
    for b in decision.blockers:
        print(f"  - {b}")
    print()
    print("Phase 3 demo complete. No AI / broker / live trading paths exercised.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

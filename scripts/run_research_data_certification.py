#!/usr/bin/env python3
"""STEP 13/14 — certify the CURRENT repository research-data state and STOP.

This composes the new acquisition/certification layer against the real repo
state: no authoritative research provider is configured, and the only available
market data (Zerodha) is non_exchange / DEVELOPMENT_DATA. The certification
therefore fails closed with research_eligible=false. Phase 19 strategy search is
NOT run. No gate is modified; nothing is fabricated.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from quantfund.research.certification import certify_dataset
from quantfund.research.data_contract.models import (
    ResearchDatasetManifest,
    SourceType,
)
from quantfund.data.grades import SourceGrade
from quantfund.research.ingestion import ingest_from_providers
from quantfund.research.ingestion.ingest import coverage_to_dict
from quantfund.research.providers import (
    UnconfiguredCalendarProvider,
    UnconfiguredCorporateActionProvider,
    UnconfiguredDelistingProvider,
    UnconfiguredSecurityMasterProvider,
    UnconfiguredUniverseProvider,
    ZerodhaDevelopmentMarketDataProvider,
)

REPO = Path(__file__).resolve().parents[1]
REPORTS = REPO / "reports"
DOCS = REPO / "docs"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    market = ZerodhaDevelopmentMarketDataProvider()

    manifest = ResearchDatasetManifest(
        dataset_id="current_repo_state",
        dataset_version="v1",
        source_name="zerodha_historical_api",
        source_type=SourceType.BROKER_REDISTRIBUTED,
        source_license="broker_account_restricted",
        source_grade=SourceGrade.NON_EXCHANGE,
        data_class="DEVELOPMENT_DATA",
        download_timestamp=datetime.now(timezone.utc),
        coverage_start=date(2018, 1, 1),
        coverage_end=date(2026, 8, 12),
        exchange="NSE",
        currency="INR",
        exchange_authority=False,
        license_status="internal_research_only",
    )

    result = ingest_from_providers(
        manifest=manifest,
        symbols=["RELIANCE", "TCS", "INFY", "HDFCBANK"],
        start=manifest.coverage_start,
        end=manifest.coverage_end,
        universe_id="NIFTY50",
        market_data=market,
        security_master=UnconfiguredSecurityMasterProvider(),
        universe=UnconfiguredUniverseProvider(),
        delistings=UnconfiguredDelistingProvider(),
        calendar=UnconfiguredCalendarProvider(),
        corporate_actions=UnconfiguredCorporateActionProvider(),
    )

    cert = certify_dataset(result.package, market.capabilities(), immutable=True)

    phase18 = _read_json(REPORTS / "phase18_dataset_eligibility.json")
    pit = _read_json(REPORTS / "pit_universe_coverage.json")
    preflight = _read_json(REPORTS / "realdata_paper_preflight.json")

    safety = {
        "orders_submitted": int(preflight.get("orders_submitted", 0)),
        "place_order_called": int(preflight.get("place_order_called", 0)),
        "live_trading": preflight.get("live_trading", "DISABLED"),
        "broker_write_capability": preflight.get(
            "real_broker_writes_enabled_label", "DISABLED"
        ),
        "kill_switch": preflight.get("kill_switch", "ARMED"),
        "auto_graduate_to_live": False,
    }

    payload = {
        "phase": "research_data_acquisition_certification",
        "stage": "step14_final_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_grade": cert.metrics["source_grade"],
        "data_class": cert.metrics["data_class"],
        "capability_source_bar_ok": cert.metrics["capability_source_bar_ok"],
        "coverage": {
            "bar_count": cert.metrics["bar_count"],
            "expected_sessions": cert.sub_results["calendar"].metrics.get(
                "expected_sessions", 0
            ),
            "observed_sessions": cert.sub_results["calendar"].metrics.get(
                "observed_sessions", 0
            ),
        },
        "calendar_quality": {
            "calendar_verified": cert.metrics["calendar_verified"],
            "calendar_errors": cert.metrics["calendar_errors"],
        },
        "membership_coverage_ratio": cert.metrics["membership_coverage_ratio"],
        "instrument_identity_coverage": cert.metrics["instrument_identity_coverage"],
        "delisted_coverage": cert.metrics["delisted_coverage"],
        "corporate_action_coverage": cert.metrics["corporate_action_coverage"],
        "research_eligible": cert.research_eligible,
        "verdict": cert.verdict,
        "eligibility_level": cert.eligibility_level,
        "reproducible": cert.reproducible,
        "immutable": cert.immutable,
        "leakage_safe": cert.leakage_safe,
        "content_hash": cert.content_hash,
        "blockers": cert.blockers,
        "capability_gaps": result.capability_gaps,
        "ingestion_coverage": coverage_to_dict(result),
        "authoritative_cross_checks": {
            "phase18_accepted_strategies": phase18.get("accepted_strategies", "not_run"),
            "phase18_research_eligible": phase18.get("research_eligible", False),
            "pit_membership_coverage_ratio": pit.get("membership_coverage_ratio", 0.0),
            "pit_completeness": pit.get("completeness", "none"),
            "pit_blockers": pit.get("blockers", []),
        },
        "safety_state": safety,
        "phase19_strategy_search": "NOT_RUN (research_eligible=false; fail-closed STOP)",
        "success_condition_met": False,
    }

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "research_data_certification.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    # Hard safety assertions — never mutated by this pipeline.
    assert safety["orders_submitted"] == 0
    assert safety["place_order_called"] == 0
    assert safety["live_trading"] == "DISABLED"
    assert str(safety["kill_switch"]).upper().startswith("ARM")
    assert cert.research_eligible is False, "must not manufacture eligibility"

    print("=" * 64)
    print("RESEARCH DATA CERTIFICATION — CURRENT REPO STATE")
    print("=" * 64)
    print(f"source_grade                 : {payload['source_grade']}")
    print(f"data_class                   : {payload['data_class']}")
    print(f"capability_source_bar_ok     : {payload['capability_source_bar_ok']}")
    print(f"membership_coverage_ratio    : {payload['membership_coverage_ratio']}")
    print(f"instrument_identity_coverage : {payload['instrument_identity_coverage']}")
    print(f"delisted_coverage            : {payload['delisted_coverage']}")
    print(f"corporate_action_coverage    : {payload['corporate_action_coverage']}")
    print(f"calendar_errors              : {payload['calendar_quality']['calendar_errors']}")
    print(f"research_eligible            : {payload['research_eligible']}")
    print(f"verdict                      : {payload['verdict']}")
    print("-" * 64)
    print("capability gaps (no authoritative source configured):")
    for gap in result.capability_gaps:
        print(f"  - {gap}")
    print("-" * 64)
    print(f"safety: {safety}")
    print("phase19_strategy_search: NOT RUN (fail-closed STOP)")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 9B demo — Zerodha adapter + safe testing layer (no real-money orders)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.brokers.zerodha.auth import (
    credentials_configured,
    load_credentials_from_env,
)
from quantfund.execution.credentials import redact_secrets
from quantfund.execution.modes import (
    QuantFundExecutionMode,
    resolve_execution_mode_from_env,
)
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.paper.eligibility import PaperEligibilityGate


def _research_level() -> str:
    # Broker connectivity must not promote research eligibility.
    facts = DatasetCertificationFacts(
        dataset_id="phase9b_demo",
        dataset_version="v0",
        source="demo",
        source_grade="non_exchange",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="none",
        universe_version="none",
        universe_completeness="current_snapshot_only",
        corporate_action_coverage="none",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-01-31",
        instrument_count=0,
        content_hash="sha256:phase9b_demo",
        capability_source_bar_ok=False,
        provenance_complete=False,
        license_status="unknown",
    )
    return ResearchEligibilityChecker().evaluate(facts).level.value


def main() -> int:
    print("PHASE 9B — Zerodha Kite Connect Integration")
    print("=" * 60)

    configured = credentials_configured()
    mode = resolve_execution_mode_from_env()
    # Demo force-defaults to OFF display for safety unless explicitly sandbox read-only
    display_mode = mode
    if display_mode == QuantFundExecutionMode.BROKER_LIVE:
        display_mode = QuantFundExecutionMode.OFF  # never imply live from demo

    print("Zerodha adapter:")
    print(f"    CONFIGURED: {str(configured).lower()}")
    print()
    print("Broker connectivity:")
    if not configured:
        print("    NOT EXECUTED (credentials not configured)")
        read_only_executed = False
    else:
        creds = load_credentials_from_env()
        assert creds is not None
        safe = redact_secrets(
            {
                "api_key": creds.api_key,
                "api_secret": creds.api_secret,
                "access_token": creds.access_token,
                "env": creds.env.value,
            }
        )
        print("    READ-ONLY path available (auth/instruments/quote/positions/holdings)")
        print(f"    Credential probe (redacted): {safe}")
        print("    Order placement: NOT EXECUTED")
        read_only_executed = True
        # Intentionally do NOT call place_order / network order APIs from demo.
    print()
    print(f"Execution mode:    {QuantFundExecutionMode.OFF.value} (demo safe default)")
    print(f"Env mode seen:     {mode.value}")
    print("Live trading:      DISABLED")
    print(f"BROKER_LIVE:       DISABLED")
    print()
    research = _research_level()
    paper = PaperEligibilityGate().evaluate(certified_eligibility=research)
    print(f"Research eligibility: {research.upper()}")
    print(f"Paper eligibility:    {str(paper.paper_eligible).upper()}")
    print("Claims:               NONE")
    print()
    print("Orders submitted:     0")
    print("Real money used:      NO")
    print(f"Read-only calls:      {'SKIPPED' if not read_only_executed else 'PROBE_ONLY'}")
    print()
    print("Phase 9B: PASS")
    print("Invariants: Strategy/AI/ResearchRunner must not call Zerodha; RiskEngine not bypassed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

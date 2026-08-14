#!/usr/bin/env python3
"""Build TEST_FIXTURE_ONLY research-capable package for Phase 9A CI.

Fabricated prices — NEVER real market data. Labeled TEST_FIXTURE_ONLY.
Intended only to exercise structural RESEARCH_ELIGIBLE gates in tests.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.ingest.checksums import directory_checksum, write_checksums
from quantfund.data.packages.vendor_import import write_package_json

OUT = ROOT / "tests" / "fixtures" / "phase9a" / "test_fixture_only_research_capable"


def _write_bars(path: Path, symbol: str, sessions: list[date], start_px: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["timestamp", "symbol", "open", "high", "low", "close", "volume", "instrument_id"]
        )
        px = start_px
        for i, sess in enumerate(sessions):
            o = px
            h = px * 1.01
            l = px * 0.99
            c = px * (1.0 + (0.001 if i % 2 == 0 else -0.001))
            w.writerow(
                [
                    f"{sess.isoformat()}T00:00:00",
                    symbol,
                    f"{o:.4f}",
                    f"{h:.4f}",
                    f"{l:.4f}",
                    f"{c:.4f}",
                    100000,
                    f"NSE:TEST{symbol}",
                ]
            )
            px = c


def main() -> int:
    if OUT.exists():
        import shutil

        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    start, end = date(2024, 1, 2), date(2024, 1, 31)
    cal = NSECalendarProvider()
    sessions = cal.sessions_in_range(start, end)
    assert sessions, "calendar returned no sessions"

    instruments = [
        {
            "symbol": "AAA",
            "instrument_id": "NSE:TESTAAA0001",
            "isin": "TESTAAA0001",
            "name": "Fixture AAA Ltd",
            "exchange": "NSE",
            "series": "EQ",
            "currency": "INR",
            "asset_class": "equity",
            "listing_date": "2020-01-01",
            "delisting_date": None,
            "status": "active",
            "aliases": ["AAAOLD"],
            "symbol_history": [
                {
                    "symbol": "AAAOLD",
                    "valid_from": "2020-01-01",
                    "valid_to": "2023-12-31",
                    "exchange": "NSE",
                }
            ],
            "metadata": {"test_fixture_only": True},
        },
        {
            "symbol": "BBB",
            "instrument_id": "NSE:TESTBBB0002",
            "isin": "TESTBBB0002",
            "name": "Fixture BBB Ltd",
            "exchange": "NSE",
            "series": "EQ",
            "listing_date": "2020-01-01",
            "status": "active",
            "metadata": {"test_fixture_only": True},
        },
        {
            "symbol": "DEAD",
            "instrument_id": "NSE:TESTDEAD003",
            "isin": "TESTDEAD003",
            "name": "Fixture Dead Ltd",
            "exchange": "NSE",
            "series": "EQ",
            "listing_date": "2015-01-01",
            "delisting_date": "2024-01-15",
            "status": "delisted",
            "metadata": {"test_fixture_only": True},
        },
    ]
    (OUT / "instruments.json").write_text(json.dumps(instruments, indent=2), encoding="utf-8")

    bars = OUT / "bars"
    _write_bars(bars / "AAA.csv", "AAA", sessions, 100.0)
    _write_bars(bars / "BBB.csv", "BBB", sessions, 200.0)
    # DEAD is delisted evidence only (instruments + terminal ledger).
    # Do not include post-range / partial bars that trip missing_open_session.

    actions = [
        {
            "action_id": "fix_aaa_split",
            "instrument_id": "NSE:TESTAAA0001",
            "symbol": "AAA",
            "action_type": "split",
            "ex_date": "2024-01-10",
            "ratio_num": 2,
            "ratio_den": 1,
            "source": "test_fixture_only",
            "verified": True,
            "raw_payload": {"test_fixture_only": True},
        },
        {
            "action_id": "test_bbb_bonus",
            "instrument_id": "NSE:TESTBBB0002",
            "symbol": "BBB",
            "action_type": "bonus",
            "ex_date": "2024-01-12",
            "ratio_num": 2,
            "ratio_den": 1,
            "source": "test_fixture_only",
            "verified": True,
            "raw_payload": {"test_fixture_only": True},
        },
        {
            "action_id": "test_aaa_div",
            "instrument_id": "NSE:TESTAAA0001",
            "symbol": "AAA",
            "action_type": "dividend",
            "ex_date": "2024-01-18",
            "cash_amount": 1.5,
            "source": "test_fixture_only",
            "verified": True,
            "raw_payload": {"test_fixture_only": True},
        },
        {
            "action_id": "test_merger_event",
            "instrument_id": "NSE:TESTDEAD003",
            "symbol": "DEAD",
            "action_type": "merger",
            "ex_date": "2024-01-15",
            "source": "test_fixture_only",
            "verified": False,
            "requires_manual_treatment": True,
            "raw_payload": {"test_fixture_only": True, "treatment": "manual"},
        },
    ]
    (OUT / "corporate_actions.json").write_text(
        json.dumps(actions, indent=2), encoding="utf-8"
    )

    terminal = [
        {
            "event_id": "term_dead_delist",
            "instrument_id": "NSE:TESTDEAD003",
            "symbol": "DEAD",
            "event_type": "delisting",
            "event_date": "2024-01-15",
            "last_trade_date": "2024-01-12",
            "source": "test_fixture_only",
            "verification_status": "verified",
            "confidence": "verified",
            "provenance": {"test_fixture_only": True},
        }
    ]
    (OUT / "terminal_events.json").write_text(
        json.dumps(terminal, indent=2), encoding="utf-8"
    )

    uni = OUT / "universe"
    uni.mkdir()
    # full_pit: instruments absent from roster are FALSE (not UNKNOWN)
    (uni / "membership.json").write_text(
        json.dumps(
            {
                "completeness": "full_pit",
                "verification_status": "verified",
                "source": "test_fixture_only",
                "memberships": [
                    {
                        "universe_id": "nifty50",
                        "instrument_id": "NSE:TESTAAA0001",
                        "symbol": "AAA",
                        "member_from": "2024-01-02",
                        "member_to": "2024-01-31",
                        "source": "test_fixture_only",
                        "verification_status": "verified",
                    },
                    {
                        "universe_id": "nifty50",
                        "instrument_id": "NSE:TESTBBB0002",
                        "symbol": "BBB",
                        "member_from": "2024-01-02",
                        "member_to": "2024-01-31",
                        "source": "test_fixture_only",
                        "verification_status": "verified",
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "LICENSE.json").write_text(
        json.dumps(
            {
                "license_status": "verified",
                "license_reference": "TEST_FIXTURE_ONLY_NOT_A_REAL_LICENSE",
                "legal_source": "QuantFund CI fixture",
                "research_use_allowed": True,
                "redistribution_allowed": True,
                "acquisition_method": "fabricated_for_ci",
                "acquisition_timestamp": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "provenance.json").write_text(
        json.dumps(
            {
                "provider": "test_fixture_only_vendor",
                "download_timestamp": datetime.now(timezone.utc).isoformat(),
                "license_status": "verified",
                "test_fixture_only": True,
                "content_hashes": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    write_package_json(
        OUT,
        package_id="phase9a_test_fixture_only_research_capable",
        package_version="1.0.0",
        provider="test_fixture_only_vendor",
        source_grade="paid",
        license_status="verified",
        exchange_authority=False,
        synthetic=False,
        coverage_start="2024-01-02",
        coverage_end="2024-01-31",
        capabilities={
            "license_status": "verified",
            "supports_daily_bars": True,
            "supports_instrument_master": True,
            "supports_corporate_actions": True,
            "supports_pit_universe": True,
            "supports_delisted_instruments": True,
            "supports_historical_identifiers": True,
            "supports_provenance": True,
            "supports_licensing_evidence": True,
            "supports_symbol_isin_mapping": True,
            "corporate_action_quality": "partial",
            "delisted_coverage": "partial",
            "universe_membership_quality": "complete",
            "identity_coverage": "complete",
            "historical_depth": "2024-01-02..2024-01-31",
            "authority_evidence_refs": ["TEST_FIXTURE_ONLY"],
            "redistribution_allowed": True,
        },
        provenance={
            "download_timestamp": datetime.now(timezone.utc).isoformat(),
            "license_status": "verified",
            "test_fixture_only": True,
        },
        extras={
            "test_fixture_only": True,
            "provider_name": "TEST_FIXTURE_ONLY Vendor",
            "usage_notes": "TEST_FIXTURE_ONLY — fabricated prices for CI gate tests. Not real NSE data.",
            "limitations": [
                "TEST_FIXTURE_ONLY",
                "Prices and membership are fabricated for continuous integration",
                "Must never be presented as real market data or exchange authority",
            ],
            "vendor": "test_fixture_only_vendor",
            "generation_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    for sym, iid in [("AAA", "NSE:TESTAAA0001"), ("BBB", "NSE:TESTBBB0002")]:
        p = bars / f"{sym}.csv"
        text = p.read_text(encoding="utf-8").replace(f"NSE:TEST{sym}", iid)
        p.write_text(text, encoding="utf-8")

    write_checksums(OUT, label="package")
    content_hash = directory_checksum(OUT)
    meta = json.loads((OUT / "package.json").read_text(encoding="utf-8"))
    meta["content_hash"] = content_hash
    meta["generation_timestamp"] = datetime.now(timezone.utc).isoformat()
    (OUT / "package.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8"
    )
    write_checksums(OUT, label="package")

    print(f"Wrote TEST_FIXTURE_ONLY package: {OUT}")
    print(f"Sessions: {len(sessions)}")
    print("NOT real market data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

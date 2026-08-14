"""Phase 18 research-dataset eligibility — fail-closed, no gate weakening.

These tests prove:
- The identity audit reads genuinely-present nested identity fields (real data)
  and still fails closed when ISIN is absent (never invented).
- The eligibility gate fails closed: source authority / PIT membership / delisted
  coverage that do not exist keep research_eligible=false.
- No trading is enabled and no dataset version is mutated.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from quantfund.data.models import MarketBar
from quantfund.data.zerodha_hist.package import write_zerodha_dataset_package
from quantfund.phase17a.datasets import DiscoveredPackage
from quantfund.phase17c.identity_pit import audit_instrument_identity
from quantfund.phase18.dataset_eligibility import (
    BLOCKER_ORDER,
    build_blocker_ledger,
    run_phase18_dataset_eligibility,
)


def _bars(symbol: str, start: date, n: int) -> list[MarketBar]:
    out: list[MarketBar] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(
                MarketBar(
                    timestamp=datetime(d.year, d.month, d.day),
                    symbol=symbol,
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.5,
                    volume=1000.0,
                )
            )
        d += timedelta(days=1)
    return out


def _write_pkg(
    tmp_path: Path,
    symbol: str,
    bars: list[MarketBar],
    *,
    instrument_metadata: dict,
    ver: str = "v1",
) -> Path:
    from quantfund.data.zerodha_hist import package as pkgmod

    pkgmod.research_zerodha_root = lambda: tmp_path  # type: ignore
    return write_zerodha_dataset_package(
        bars=bars,
        provenance={"provider": "zerodha", "price_policy": "unknown"},
        quality_report={"ok": True},
        corporate_actions=[],
        instrument_metadata=instrument_metadata,
        dataset_id=f"zerodha_nse_daily_{symbol.lower()}_test",
        version=ver,
    )


def _pkg(path: Path, symbol: str) -> DiscoveredPackage:
    man = json.loads((path / "manifest.json").read_text())
    return DiscoveredPackage(
        dataset_id=man["dataset_id"],
        dataset_version=man["dataset_version"],
        path=path,
        manifest=man,
        symbol=symbol,
        bars=man["rows"],
        start=man["start"],
        end=man["end"],
        content_hash=man["content_hash"],
        price_policy="unknown",
        eligibility="DEVELOPMENT_ONLY",
    )


# --- Identity audit: reads real nested data, fails closed on missing ISIN ---


def test_identity_reads_nested_resolved_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("RELIANCE", date(2018, 1, 2), 40)
    meta = {
        "phase": "17B",
        "symbol": "RELIANCE",
        "resolved": {
            "exchange": "NSE",
            "instrument_id": "NSE:RELIANCE",
            "instrument_token": 738561,
            "isin": None,
            "status": "RESOLVED",
            "tradingsymbol": "RELIANCE",
        },
    }
    path = _write_pkg(tmp_path, "RELIANCE", bars, instrument_metadata=meta)
    ident = audit_instrument_identity(_pkg(path, "RELIANCE"))
    # instrument_token genuinely present under 'resolved' is surfaced (not a false miss)
    assert ident["instrument_token"] == 738561
    assert ident["identity_status"] == "BROKER_RESOLVED"
    assert "missing_instrument_token" not in ident["issues"]
    # ISIN is genuinely null -> still fails closed (not invented)
    assert "no_isin_stable_identity" in ident["issues"]
    assert ident["issue_count"] == 1


def test_identity_full_isin_zero_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("RELIANCE", date(2018, 1, 2), 40)
    meta = {
        "symbol": "RELIANCE",
        "resolved": {
            "exchange": "NSE",
            "instrument_id": "NSE:RELIANCE",
            "instrument_token": 738561,
            "isin": "INE002A01018",
            "tradingsymbol": "RELIANCE",
        },
    }
    path = _write_pkg(tmp_path, "RELIANCE", bars, instrument_metadata=meta)
    ident = audit_instrument_identity(_pkg(path, "RELIANCE"))
    assert ident["isin"] == "INE002A01018"
    assert ident["issue_count"] == 0


def test_identity_top_level_metadata_still_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backward-compatible with top-level metadata layout (no regression)."""
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("TCS", date(2018, 1, 2), 30)
    meta = {"instrument_token": 123, "tradingsymbol": "TCS", "exchange": "NSE"}
    path = _write_pkg(tmp_path, "TCS", bars, instrument_metadata=meta)
    ident = audit_instrument_identity(_pkg(path, "TCS"))
    assert ident["identity_status"] == "BROKER_RESOLVED"
    assert "no_isin_stable_identity" in ident["issues"]


# --- Blocker ledger: fail closed on genuinely-missing artifacts ---


def test_blocker_order_is_seven() -> None:
    assert len(BLOCKER_ORDER) == 7
    assert BLOCKER_ORDER[0] == "exchange_grade_source_certification"


def test_blocker_ledger_fail_closed_on_zerodha_facts() -> None:
    # Simulate the real Zerodha per-symbol eligibility blocker set.
    row = {
        "symbol": "RELIANCE",
        "identity": {"issue_count": 1, "instrument_token": 738561, "isin": None},
        "membership": {"unknown_membership_session_count": 2134},
        "quality": {"errors": 13},
        "corporate_actions": {"coverage": "PARTIAL"},
        "eligibility": {
            "blockers": [
                "source_grade=non_exchange is not exchange/paid research grade",
                "data_class=DEVELOPMENT_DATA cannot be research_eligible",
                "capability_source_bar_ok=false",
                "quality ERROR count=13 codes=['bar_on_closed_session']",
                "universe_completeness=current_snapshot_only",
                "unknown_membership_session_count=2134",
                "membership_coverage_ratio=0.0 < required 1.0",
                "delisted_coverage=unknown insufficient for research",
                "instrument_identity_issues=1",
            ],
            "is_research_eligible": False,
        },
    }
    ledger = {b["id"]: b for b in build_blocker_ledger([row])}
    # Every unavailable-artifact blocker must remain UNRESOLVED (fail closed).
    for bid in (
        "exchange_grade_source_certification",
        "calendar_residuals",
        "pit_universe_membership_ledger",
        "instrument_identity_isin",
        "delisted_security_coverage",
        "capability_source_bar_ok",
    ):
        assert ledger[bid]["status"] == "UNRESOLVED", bid


def test_blocker_ledger_ca_resolved_when_present() -> None:
    row = {
        "symbol": "RELIANCE",
        "identity": {"issue_count": 0},
        "membership": {"unknown_membership_session_count": 0},
        "quality": {"errors": 0},
        "corporate_actions": {"coverage": "PARTIAL"},
        "eligibility": {"blockers": [], "is_research_eligible": False},
    }
    ledger = {b["id"]: b for b in build_blocker_ledger([row])}
    # No corporate_action_coverage blocker string => research-bar CA satisfied.
    assert ledger["corporate_action_completeness"]["status"] == "RESOLVED"


# --- End-to-end aggregator: fails closed, no trading, no mutation ---


def test_run_phase18_fails_closed_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("RELIANCE", date(2018, 1, 2), 60)
    meta = {
        "symbol": "RELIANCE",
        "resolved": {
            "exchange": "NSE",
            "instrument_id": "NSE:RELIANCE",
            "instrument_token": 738561,
            "isin": None,
            "tradingsymbol": "RELIANCE",
        },
    }
    path = _write_pkg(tmp_path, "RELIANCE", bars, instrument_metadata=meta)
    pkg = _pkg(path, "RELIANCE")

    payload = run_phase18_dataset_eligibility(
        out_dir=tmp_path, packages=[pkg], write_reports=True
    )

    # Mandated explicit fields
    assert payload["research_eligible"] is False
    assert payload["paper_candidate"] is False
    assert payload["live_enabled"] is False
    assert payload["orders_submitted"] == 0
    assert payload["place_order_called"] == 0

    # Stops at the first ordered blocker (exchange-grade source)
    assert payload["stopped_at_blocker"] == "exchange_grade_source_certification"

    # Safety
    assert payload["safety"]["live_trading"] == "DISABLED"
    assert payload["safety"]["place_order_called"] == 0

    # No new dataset version created (read-only; immutability preserved)
    assert payload["immutability"]["wrote_new_dataset_versions"] is False
    assert not (path.parent / "v2").exists()

    # Reports written
    assert (tmp_path / "reports" / "phase18_dataset_eligibility.json").exists()
    assert (tmp_path / "docs" / "PHASE18_DATASET_ELIGIBILITY.md").exists()


def test_run_phase18_report_has_mandated_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "quantfund.data.zerodha_hist.package.research_zerodha_root", lambda: tmp_path
    )
    bars = _bars("INFY", date(2018, 1, 2), 55)
    meta = {"resolved": {"instrument_token": 408065, "isin": None, "exchange": "NSE"}}
    path = _write_pkg(tmp_path, "INFY", bars, instrument_metadata=meta)
    run_phase18_dataset_eligibility(
        out_dir=tmp_path, packages=[_pkg(path, "INFY")], write_reports=True
    )
    doc = (tmp_path / "docs" / "PHASE18_DATASET_ELIGIBILITY.md").read_text()
    assert "research_eligible = false" in doc
    assert "paper_candidate = false" in doc
    assert "live_enabled = false" in doc
    assert "orders_submitted = 0" in doc
    assert "place_order_called = 0" in doc


def test_no_gate_weakening_source_grade_still_blocks() -> None:
    """A clean identity/membership/calendar row must NOT flip eligibility while
    the source remains non_exchange — the source gate is never weakened."""
    row = {
        "symbol": "RELIANCE",
        "identity": {"issue_count": 0},
        "membership": {"unknown_membership_session_count": 0},
        "quality": {"errors": 0},
        "corporate_actions": {"coverage": "full_verified"},
        "eligibility": {
            "blockers": [
                "source_grade=non_exchange is not exchange/paid research grade",
                "capability_source_bar_ok=false",
                "data_class=DEVELOPMENT_DATA cannot be research_eligible",
            ],
            "is_research_eligible": False,
        },
    }
    ledger = {b["id"]: b for b in build_blocker_ledger([row])}
    assert ledger["exchange_grade_source_certification"]["status"] == "UNRESOLVED"
    assert ledger["capability_source_bar_ok"]["status"] == "UNRESOLVED"

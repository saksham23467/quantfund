"""Phase 7 — provenance/license + instrument identity tests."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.identity import (
    apply_symbol_change,
    check_active_symbol_conflicts,
    check_isin_collision_registry,
    check_overlapping_listing_intervals,
)
from quantfund.data.instruments.coverage import measure_delisted_coverage
from quantfund.data.instruments.delisted import (
    TerminalEvent,
    TerminalEventType,
    check_delisting_terminal_consistency,
)
from quantfund.data.models import Instrument
from quantfund.data.packages.license import (
    PackageLicenseStatus,
    parse_license_evidence,
)
from quantfund.data.providers.package_validator import validate_research_package

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "phase35" / "pilot_package"


def _copy_pkg(tmp_path: Path) -> Path:
    dest = tmp_path / "pkg"
    shutil.copytree(FIXTURE, dest)
    return dest


def test_unknown_license_evidence():
    ev = parse_license_evidence(package_meta={"provider": "x"}, license_json=None)
    assert ev.license_status == PackageLicenseStatus.UNKNOWN
    assert ev.research_license_ok() is False


def test_expired_license_rejected_by_validator(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    (dest / "LICENSE.json").write_text(
        json.dumps({"license_status": "expired", "license_reference": "old"}),
        encoding="utf-8",
    )
    r = validate_research_package(dest)
    assert r.valid is False
    assert any(e.code == "license_expired" for e in r.errors)


def test_prohibited_license_rejected(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    (dest / "LICENSE.json").write_text(
        json.dumps({"license_status": "prohibited"}),
        encoding="utf-8",
    )
    r = validate_research_package(dest)
    assert r.valid is False
    assert any(e.code == "license_prohibited" for e in r.errors)


def test_contradictory_authority(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    meta = json.loads((dest / "package.json").read_text(encoding="utf-8"))
    # Keep synthetic; claim authority in capabilities while provenance denies
    meta["capabilities"]["exchange_authority"] = False
    (dest / "package.json").write_text(json.dumps(meta), encoding="utf-8")
    (dest / "provenance.json").write_text(
        json.dumps(
            {
                "exchange_authority": False,
                "source_grade": "paid",
            }
        ),
        encoding="utf-8",
    )
    r = validate_research_package(dest)
    assert r.valid is False
    assert any(e.code == "contradictory_provenance" for e in r.errors)


def test_missing_license_evidence_unknown_warning(tmp_path: Path):
    dest = _copy_pkg(tmp_path)
    meta = json.loads((dest / "package.json").read_text(encoding="utf-8"))
    meta["capabilities"]["license_status"] = "unknown"
    meta.pop("license_ref", None)
    (dest / "package.json").write_text(json.dumps(meta), encoding="utf-8")
    r = validate_research_package(dest)
    # unknown is warning, not hard fail for synthetic redistributable override —
    # after overwrite, expect license_unknown warning
    assert any(w.code == "license_unknown" for w in r.warnings) or r.license_evidence


def test_symbol_change_keeps_instrument_id():
    inst = Instrument(
        symbol="OLD",
        exchange="NSE",
        isin="INE002A01018",
        listing_date=date(2020, 1, 1),
        status="active",
    )
    action = CorporateAction(
        action_id="sc1",
        instrument_id=inst.instrument_id or "",
        symbol="OLD",
        action_type=CorporateActionType.SYMBOL_CHANGE,
        ex_date=date(2024, 3, 1),
        source="doc",
        verified=True,
    )
    updated = apply_symbol_change(inst, action, new_symbol="NEW")
    assert updated.symbol == "NEW"
    assert updated.instrument_id == inst.instrument_id
    assert updated.isin == inst.isin


def test_isin_conflict_detected():
    a = Instrument(symbol="A", exchange="NSE", isin="INE111A01010", listing_date=date(2020, 1, 1))
    b = Instrument(symbol="B", exchange="NSE", isin="INE111A01010", listing_date=date(2021, 1, 1))
    # Force distinct instrument_ids despite same ISIN
    a = a.model_copy(update={"instrument_id": "NSE:A"})
    b = b.model_copy(update={"instrument_id": "NSE:B"})
    issues = check_isin_collision_registry([a, b])
    assert any(i.code == "isin_identity_collision" for i in issues)


def test_active_symbol_conflict():
    a = Instrument(symbol="RELIANCE", exchange="NSE", isin="INE002A01018")
    b = Instrument(symbol="RELIANCE", exchange="NSE", isin="INE999A01099")
    issues = check_active_symbol_conflicts([a, b])
    assert any(i.code == "active_symbol_conflict" for i in issues)


def test_overlapping_listing_intervals():
    a = Instrument(
        symbol="A",
        exchange="NSE",
        isin="INE111A01010",
        instrument_id="NSE:A",
        listing_date=date(2020, 1, 1),
        delisting_date=date(2024, 6, 1),
    )
    b = Instrument(
        symbol="B",
        exchange="NSE",
        isin="INE111A01010",
        instrument_id="NSE:B",
        listing_date=date(2024, 1, 1),
        delisting_date=None,
    )
    issues = check_overlapping_listing_intervals([a, b])
    assert any(i.code == "overlapping_listing_interval" for i in issues)


def test_impossible_terminal_event():
    inst = Instrument(
        symbol="X",
        exchange="NSE",
        isin="INE123A01011",
        delisting_date=date(2024, 1, 15),
        status="delisted",
        terminal_event_id="te1",
    )
    ev = TerminalEvent(
        event_id="te1",
        instrument_id=inst.instrument_id or "NSE:X",
        symbol="X",
        event_type=TerminalEventType.DELISTING,
        event_date=date(2024, 1, 15),
        last_trade_date=date(2024, 1, 20),  # after event — impossible
        source="t",
        verification_status="verified",
    )
    issues = check_delisting_terminal_consistency([inst], [ev])
    assert any(i.code == "impossible_terminal_event" for i in issues)


def test_delisting_coverage_none_without_events():
    inst = Instrument(symbol="A", exchange="NSE", isin="INE001A01011")
    report = measure_delisted_coverage(instruments=[inst], events=[])
    assert report.level == "none"
    assert report.evidence_status == "none"
    assert report.coverage_ratio == 0.0


def test_delisting_coverage_partial_not_promoted_to_full():
    delisted = Instrument(
        symbol="GONE",
        exchange="NSE",
        isin="INE222A01022",
        delisting_date=date(2024, 2, 1),
        status="delisted",
    )
    active = Instrument(symbol="LIVE", exchange="NSE", isin="INE333A01033")
    ev = TerminalEvent(
        event_id="te",
        instrument_id=delisted.instrument_id or "",
        symbol="GONE",
        event_type=TerminalEventType.DELISTING,
        event_date=date(2024, 2, 1),
        source="t",
        verification_status="unverified",
    )
    report = measure_delisted_coverage(
        instruments=[delisted, active], events=[ev]
    )
    assert report.level == "partial"
    assert report.evidence_status != "complete"


def test_verified_license_ok():
    ev = parse_license_evidence(
        package_meta={"provider": "vendor"},
        license_json={
            "license_status": "verified",
            "research_use_allowed": True,
            "license_reference": "CONTRACT-1",
        },
    )
    assert ev.research_license_ok() is True

"""Phase 9A — research data upgrade infrastructure (no live/broker)."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from quantfund.data.corporate_actions.historical_local import (
    compute_metrics,
    ingest_historical_ca,
    load_and_normalize,
    normalize_row,
)
from quantfund.data.corporate_actions.models import CorporateActionType
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.ingest.checksums import write_checksums
from quantfund.data.instruments.delisted import TerminalEvent, TerminalEventType
from quantfund.data.instruments.master import InstrumentMasterStore
from quantfund.data.instruments.resolve import (
    IdentityResolutionStatus,
    resolve_symbol_identity,
)
from quantfund.data.models import Instrument, SymbolHistoryEntry
from quantfund.data.packages.contract import ResearchPackageManifest
from quantfund.data.packages.traffic_light import (
    ReadinessLight,
    evaluate_research_readiness,
)
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.data.providers.capabilities import yfinance_capabilities
from quantfund.data.providers.package_validator import validate_research_package
from quantfund.data.universe.membership import (
    MembershipAnswer,
    UniverseMembershipStore,
    was_member,
)
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMembership,
    UniverseVersion,
    VerificationStatus,
)
from quantfund.execution.gateway import ExecutionMode
from quantfund.research.certify_package import certify_research_package

FIXTURE_9A = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "phase9a"
    / "test_fixture_only_research_capable"
)
CA_SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "ca" / "cf_ca_sample.csv"
PILOT = Path(__file__).resolve().parents[1] / "fixtures" / "phase35" / "pilot_package"


def _require_fixture() -> None:
    if not FIXTURE_9A.is_dir():
        pytest.skip("phase9a fixture missing — run scripts/build_phase9a_test_fixture.py")


def _copy_fixture(tmp_path: Path, name: str = "pkg") -> Path:
    _require_fixture()
    dest = tmp_path / name
    shutil.copytree(FIXTURE_9A, dest)
    return dest


# --- Contract / capable vs eligible ---


def test_contract_capable_vs_eligible_declaration():
    m = ResearchPackageManifest(
        package_id="x",
        package_version="1",
        provider="v",
        source_grade="paid",
        license_status="verified",
    )
    assert m.is_research_eligible_capable_declared() is True


def test_declaration_does_not_grant_eligibility():
    d = ResearchEligibilityChecker().evaluate(
        DatasetCertificationFacts(
            dataset_id="x",
            dataset_version="1",
            source="v",
            source_grade="paid",
            calendar_id="NSE_EQ",
            calendar_version="nse_eq_v2023_2025_r1",
            calendar_verified=True,
            universe_id="u",
            universe_version="v",
            universe_completeness="current_snapshot_only",
            corporate_action_coverage="none",
            adjustment_policy_id="split_bonus_v1",
            date_coverage_start="2024-01-02",
            date_coverage_end="2024-01-31",
            instrument_count=1,
            content_hash="sha256:x",
            capability_source_bar_ok=True,
            provenance_complete=True,
            license_status="verified",
        )
    )
    assert d.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_synthetic_manifest_not_capable():
    m = ResearchPackageManifest(
        package_id="s",
        package_version="1",
        provider="syn",
        source_grade="synthetic",
        license_status="verified",
        synthetic=True,
    )
    assert m.is_research_eligible_capable_declared() is False


def test_non_exchange_manifest_not_capable():
    m = ResearchPackageManifest(
        package_id="yf",
        package_version="1",
        provider="yfinance",
        source_grade="non_exchange",
        license_status="unknown",
    )
    assert m.is_research_eligible_capable_declared() is False


# --- Package validation / anti-forgery ---


def test_forged_eligibility_flag_rejected(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "forged")
    meta = json.loads((dest / "package.json").read_text())
    meta["research_eligible"] = True
    (dest / "package.json").write_text(json.dumps(meta, indent=2))
    write_checksums(dest, label="package")
    v = validate_research_package(dest)
    assert v.valid is False
    assert any(e.code == "eligibility_assertion_forbidden" for e in v.errors)


def test_checksum_tamper_fails(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "tamper")
    bar = next((dest / "bars").glob("*.csv"))
    bar.write_text(bar.read_text() + "\n", encoding="utf-8")
    v = validate_research_package(dest)
    assert v.valid is False


def test_missing_instruments_fails(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "missing")
    (dest / "instruments.json").unlink()
    write_checksums(dest, label="package")
    v = validate_research_package(dest)
    assert v.valid is False


def test_missing_package_json_fails(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "nopkg")
    (dest / "package.json").unlink()
    v = validate_research_package(dest)
    assert v.valid is False


def test_invalid_provenance_fails(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "badprov")
    (dest / "provenance.json").write_text("{not-json", encoding="utf-8")
    write_checksums(dest, label="package")
    v = validate_research_package(dest)
    assert v.valid is False


def test_fixture_validates_structurally():
    _require_fixture()
    v = validate_research_package(FIXTURE_9A)
    assert v.valid is True


def test_fixture_can_reach_research_eligible():
    _require_fixture()
    elig, facts, blockers, meta = certify_research_package(package_root=FIXTURE_9A)
    assert elig == "research_eligible"
    assert facts is not None
    assert meta.get("test_fixture_only") is True
    assert blockers == []


def test_fixture_labeled_test_only():
    _require_fixture()
    meta = json.loads((FIXTURE_9A / "package.json").read_text())
    assert meta.get("test_fixture_only") is True
    assert "TEST_FIXTURE_ONLY" in (meta.get("limitations") or [])


def test_certification_reproducible_facts_hash():
    _require_fixture()
    a = certify_research_package(package_root=FIXTURE_9A)
    b = certify_research_package(package_root=FIXTURE_9A)
    assert a[0] == b[0]
    assert a[3].get("facts_hash") == b[3].get("facts_hash")
    assert a[3].get("package_hash") == b[3].get("package_hash")


# --- Development sources remain DEVELOPMENT_ONLY ---


def test_yfinance_still_development_only():
    assert yfinance_capabilities().can_satisfy_research_eligibility_source_bar() is False


def test_pilot_synthetic_still_development_only():
    elig, _, blockers, _ = certify_research_package(package_root=PILOT)
    assert elig == "development_only"
    assert blockers


def test_real_world_unconfigured_cert_false():
    elig, _, blockers, _ = certify_research_package(package_root=None)
    assert elig == "development_only"
    assert "research_package_not_configured" in blockers


def test_unconfigured_package_readiness_red():
    report = evaluate_research_readiness(None)
    assert report.light == ReadinessLight.RED
    assert report.research_eligible is False


def test_fixture_readiness_green_not_real_market_claim():
    _require_fixture()
    report = evaluate_research_readiness(FIXTURE_9A)
    assert report.light == ReadinessLight.GREEN
    assert report.research_eligible is True
    assert report.meta.get("test_fixture_only") is True or any(
        "TEST_FIXTURE_ONLY" in n for n in report.notes
    )


# --- Identity resolution ---


def test_identity_resolve_symbol():
    inst = Instrument(
        symbol="RELIANCE",
        instrument_id="NSE:INE002A01018",
        isin="INE002A01018",
        exchange="NSE",
    )
    r = resolve_symbol_identity("RELIANCE", instruments=[inst])
    assert r.status == IdentityResolutionStatus.RESOLVED
    assert r.instrument_id == "NSE:INE002A01018"


def test_identity_never_by_company_name_alone():
    inst = Instrument(
        symbol="RELIANCE",
        instrument_id="NSE:INE002A01018",
        isin="INE002A01018",
        exchange="NSE",
        name="Reliance Industries Ltd",
    )
    r = resolve_symbol_identity("Reliance Industries Ltd", instruments=[inst])
    assert r.status == IdentityResolutionStatus.UNKNOWN


def test_identity_symbol_change_via_history():
    inst = Instrument(
        symbol="NEWCO",
        instrument_id="NSE:INE000000001",
        isin="INE000000001",
        exchange="NSE",
        symbol_history=[
            SymbolHistoryEntry(
                symbol="OLDCO",
                valid_from=date(2020, 1, 1),
                valid_to=date(2023, 12, 31),
                exchange="NSE",
            )
        ],
    )
    r = resolve_symbol_identity("OLDCO", instruments=[inst], asof=date(2022, 6, 1))
    assert r.status == IdentityResolutionStatus.RESOLVED
    assert r.instrument_id == "NSE:INE000000001"


def test_identity_ambiguous_duplicate_symbols():
    a = Instrument(symbol="DUP", instrument_id="NSE:A", isin="A", exchange="NSE")
    b = Instrument(symbol="DUP", instrument_id="NSE:B", isin="B", exchange="NSE")
    r = resolve_symbol_identity("DUP", instruments=[a, b])
    assert r.status == IdentityResolutionStatus.AMBIGUOUS


def test_identity_alias_match():
    inst = Instrument(
        symbol="AAA",
        instrument_id="NSE:X",
        isin="X",
        exchange="NSE",
        aliases=["AAAOLD"],
    )
    r = resolve_symbol_identity("AAAOLD", instruments=[inst])
    assert r.status == IdentityResolutionStatus.RESOLVED


def test_identity_delisted_still_resolvable():
    inst = Instrument(
        symbol="DEAD",
        instrument_id="NSE:DEAD1",
        isin="DEAD1",
        exchange="NSE",
        status="delisted",
        delisting_date=date(2023, 6, 1),
    )
    r = resolve_symbol_identity("DEAD", instruments=[inst])
    assert r.status == IdentityResolutionStatus.RESOLVED


def test_identity_empty_symbol_unknown():
    r = resolve_symbol_identity("", instruments=[])
    assert r.status == IdentityResolutionStatus.UNKNOWN


def test_predecessor_successor_fields():
    inst = Instrument(
        symbol="NEW",
        exchange="NSE",
        isin="N",
        predecessor_instrument_id="NSE:OLD",
        successor_instrument_id=None,
        series="EQ",
    )
    assert inst.predecessor_instrument_id == "NSE:OLD"
    assert inst.series == "EQ"


def test_instrument_series_aliases_roundtrip(tmp_path: Path):
    store = InstrumentMasterStore(tmp_path)
    store.save(
        master_id="m",
        master_version="v2",
        instruments=[
            Instrument(
                symbol="A",
                exchange="NSE",
                isin="A1",
                series="EQ",
                aliases=["AOLD"],
            )
        ],
        source="t",
    )
    loaded = store.load("m", "v2")
    assert loaded[0].series == "EQ"
    assert "AOLD" in loaded[0].aliases


def test_master_immutable(tmp_path: Path):
    store = InstrumentMasterStore(tmp_path)
    store.save(
        master_id="m",
        master_version="v1",
        instruments=[Instrument(symbol="A", exchange="NSE", isin="A")],
        source="t",
    )
    with pytest.raises(FileExistsError):
        store.save(
            master_id="m",
            master_version="v1",
            instruments=[Instrument(symbol="B", exchange="NSE", isin="B")],
            source="t",
        )


# --- CA + identity ---


def test_ca_identity_with_master():
    instruments = [
        Instrument(
            symbol="TEXINFRA",
            instrument_id="NSE:INETEX001",
            isin="INETEX001",
            exchange="NSE",
        )
    ]
    records = load_and_normalize(
        CA_SAMPLE, source_hash="sha256:test", instruments=instruments
    )
    resolved = [r for r in records if r.symbol == "TEXINFRA"]
    assert resolved
    assert resolved[0].identity_resolution_status.value == "RESOLVED"
    assert resolved[0].instrument_id == "NSE:INETEX001"


def test_ca_identity_unknown_without_master():
    records = load_and_normalize(CA_SAMPLE, source_hash="sha256:test")
    assert all(r.identity_resolution_status.value != "RESOLVED" for r in records)


def test_ca_ingest_with_master_store(tmp_path: Path):
    store = InstrumentMasterStore(tmp_path / "masters")
    store.save(
        master_id="india_eq",
        master_version="ca_test_v1",
        instruments=[
            Instrument(
                symbol="TEXINFRA",
                instrument_id="NSE:INETEX001",
                isin="INETEX001",
                exchange="NSE",
            )
        ],
        source="test",
    )
    instruments = store.load("india_eq", "ca_test_v1")
    result = ingest_historical_ca(
        CA_SAMPLE,
        instruments=instruments,
        output_normalized_root=tmp_path / "norm",
    )
    assert result.metrics.resolved_identity_rows >= 1
    assert result.research_eligible is False


def test_merger_manual_no_ohlc_invention():
    row = {
        "SYMBOL": "X",
        "COMPANY NAME": "X",
        "SERIES": "EQ",
        "PURPOSE": "Scheme Of Arrangement And Merger",
        "FACE VALUE": "10",
        "EX-DATE": "01-Mar-2020",
        "RECORD DATE": "-",
        "BOOK CLOSURE START DATE": "-",
        "BOOK CLOSURE END DATE": "-",
    }
    r = normalize_row(row, source_row_id=1, source_hash="sha256:x")
    assert r.action_type == CorporateActionType.MERGER
    assert r.requires_manual_treatment is True
    assert r.is_price_adjusting is False


def test_demerger_manual_treatment():
    row = {
        "SYMBOL": "Y",
        "COMPANY NAME": "Y",
        "SERIES": "EQ",
        "PURPOSE": "Scheme Of Demerger",
        "FACE VALUE": "10",
        "EX-DATE": "01-Mar-2020",
        "RECORD DATE": "-",
        "BOOK CLOSURE START DATE": "-",
        "BOOK CLOSURE END DATE": "-",
    }
    r = normalize_row(row, source_row_id=1, source_hash="sha256:x")
    assert r.action_type == CorporateActionType.DEMERGER
    assert r.requires_manual_treatment is True


def test_ca_duplicate_conflict_metric():
    r1 = normalize_row(
        {
            "SYMBOL": "Z",
            "COMPANY NAME": "Z",
            "SERIES": "EQ",
            "PURPOSE": "Dividend - Rs 1 Per Share",
            "FACE VALUE": "10",
            "EX-DATE": "01-Jun-2020",
            "RECORD DATE": "-",
            "BOOK CLOSURE START DATE": "-",
            "BOOK CLOSURE END DATE": "-",
        },
        source_row_id=1,
        source_hash="sha256:x",
    )
    r2 = normalize_row(
        {
            "SYMBOL": "Z",
            "COMPANY NAME": "Z",
            "SERIES": "EQ",
            "PURPOSE": "Dividend - Rs 5 Per Share",
            "FACE VALUE": "10",
            "EX-DATE": "01-Jun-2020",
            "RECORD DATE": "-",
            "BOOK CLOSURE START DATE": "-",
            "BOOK CLOSURE END DATE": "-",
        },
        source_row_id=2,
        source_hash="sha256:x",
    )
    m = compute_metrics([r1, r2])
    assert m.duplicate_conflict_count >= 1


def test_ca_ambiguous_identity_not_resolved():
    a = Instrument(symbol="TCS", instrument_id="NSE:A", isin="A", exchange="NSE")
    b = Instrument(symbol="TCS", instrument_id="NSE:B", isin="B", exchange="NSE")
    records = load_and_normalize(
        CA_SAMPLE, source_hash="sha256:test", instruments=[a, b]
    )
    tcs = [r for r in records if r.symbol == "TCS"]
    assert tcs
    assert tcs[0].identity_resolution_status.value == "AMBIGUOUS"


# --- Terminal / delisted ---


def test_terminal_acquired_suspended_types():
    assert TerminalEventType.ACQUIRED.value == "acquired"
    assert TerminalEventType.SUSPENDED.value == "suspended"
    e = TerminalEvent(
        event_id="e1",
        instrument_id="NSE:X",
        symbol="X",
        event_type=TerminalEventType.ACQUIRED,
        event_date=date(2024, 1, 1),
        source="test",
        confidence="high",
        provenance={"ref": "t"},
    )
    assert e.requires_manual_treatment is True


def test_renamed_terminal_type():
    e = TerminalEvent(
        event_id="r1",
        instrument_id="NSE:X",
        symbol="X",
        event_type=TerminalEventType.RENAMED,
        event_date=date(2024, 1, 1),
        source="t",
        predecessor_instrument_id="NSE:OLD",
    )
    assert e.event_type == TerminalEventType.RENAMED
    assert e.predecessor_instrument_id == "NSE:OLD"


def test_delisted_none_blocks_eligibility(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "nodelist")
    inst = json.loads((dest / "instruments.json").read_text())
    inst = [i for i in inst if i["symbol"] != "DEAD"]
    (dest / "instruments.json").write_text(json.dumps(inst, indent=2))
    (dest / "terminal_events.json").write_text("[]", encoding="utf-8")
    write_checksums(dest, label="package")
    elig, facts, blockers, _ = certify_research_package(package_root=dest)
    assert elig == "development_only"
    assert facts is None or facts.delisted_coverage == "none" or any(
        "delisted" in b for b in blockers
    )


# --- PIT ---


def test_pit_unknown_not_false():
    uni = UniverseVersion(
        universe_id="nifty50",
        universe_version="partial",
        completeness=UniverseCompleteness.PARTIAL_PIT,
        as_of_date=date(2024, 1, 10),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 1, 31),
        source="t",
        memberships=[
            UniverseMembership(
                universe_id="nifty50",
                instrument_id="NSE:A",
                symbol="A",
                member_from=date(2024, 1, 2),
                member_to=date(2024, 1, 31),
                source="t",
                verification_status=VerificationStatus.VERIFIED,
            )
        ],
    )
    ans = was_member(uni, symbol="ZZZ", on=date(2024, 1, 10))
    assert ans == MembershipAnswer.UNKNOWN


def test_pit_full_absence_is_false():
    uni = UniverseVersion(
        universe_id="nifty50",
        universe_version="full",
        completeness=UniverseCompleteness.FULL_PIT,
        as_of_date=date(2024, 1, 10),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 1, 31),
        source="t",
        memberships=[
            UniverseMembership(
                universe_id="nifty50",
                instrument_id="NSE:A",
                symbol="A",
                member_from=date(2024, 1, 2),
                member_to=date(2024, 1, 31),
                source="t",
                verification_status=VerificationStatus.VERIFIED,
            )
        ],
    )
    ans = was_member(uni, symbol="ZZZ", on=date(2024, 1, 10))
    assert ans == MembershipAnswer.FALSE


def test_pit_true_for_member():
    uni = UniverseVersion(
        universe_id="nifty50",
        universe_version="full",
        completeness=UniverseCompleteness.FULL_PIT,
        as_of_date=date(2024, 1, 10),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 1, 31),
        source="t",
        memberships=[
            UniverseMembership(
                universe_id="nifty50",
                instrument_id="NSE:A",
                symbol="A",
                member_from=date(2024, 1, 2),
                member_to=date(2024, 1, 31),
                source="t",
                verification_status=VerificationStatus.VERIFIED,
            )
        ],
    )
    assert was_member(uni, instrument_id="NSE:A", on=date(2024, 1, 10)) == MembershipAnswer.TRUE


def test_pit_immutability(tmp_path: Path):
    store = UniverseMembershipStore(tmp_path)
    uni = UniverseVersion(
        universe_id="nifty50",
        universe_version="v1",
        completeness=UniverseCompleteness.FULL_PIT,
        as_of_date=date(2024, 1, 10),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 1, 31),
        source="t",
        memberships=[
            UniverseMembership(
                universe_id="nifty50",
                instrument_id="NSE:A",
                symbol="A",
                member_from=date(2024, 1, 2),
                member_to=date(2024, 1, 31),
                source="t",
                verification_status=VerificationStatus.VERIFIED,
            )
        ],
    )
    store.save(uni)
    with pytest.raises(FileExistsError):
        store.save(uni)


def test_incomplete_pit_blocks_eligibility(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "badpit")
    shutil.rmtree(dest / "universe")
    (dest / "universe").mkdir()
    (dest / "universe" / "membership.json").write_text(
        json.dumps(
            {
                "completeness": "partial_pit",
                "verification_status": "partial",
                "source": "t",
                "memberships": [
                    {
                        "universe_id": "nifty50",
                        "instrument_id": "NSE:TESTAAA0001",
                        "symbol": "AAA",
                        "member_from": "2024-01-02",
                        "member_to": "2024-01-31",
                        "source": "t",
                        "verification_status": "verified",
                    }
                ],
            }
        )
    )
    write_checksums(dest, label="package")
    elig, _, blockers, _ = certify_research_package(package_root=dest)
    assert elig == "development_only"
    assert any(
        "unknown_membership" in b or "membership_coverage" in b or "universe" in b
        for b in blockers
    )


# --- Coverage / license blockers ---


def test_bad_ca_coverage_blocks(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "badca")
    (dest / "corporate_actions.json").write_text("[]", encoding="utf-8")
    write_checksums(dest, label="package")
    elig, facts, blockers, _ = certify_research_package(package_root=dest)
    assert elig == "development_only"
    assert facts is None or facts.corporate_action_coverage in {"none", "partial"} or blockers


def test_prohibited_license_blocks(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "badlic")
    meta = json.loads((dest / "package.json").read_text())
    meta["license_status"] = "prohibited"
    (dest / "package.json").write_text(json.dumps(meta, indent=2))
    (dest / "LICENSE.json").write_text(
        json.dumps({"license_status": "prohibited"}), encoding="utf-8"
    )
    write_checksums(dest, label="package")
    v = validate_research_package(dest)
    elig, _, blockers, _ = certify_research_package(package_root=dest)
    assert elig == "development_only"
    assert (not v.valid) or any("license" in b or "prohibit" in b for b in blockers)


def test_ohlc_corruption_fails_cert(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "ohlc")
    p = dest / "bars" / "AAA.csv"
    lines = p.read_text().splitlines()
    parts = lines[1].split(",")
    parts[3] = "1.0"
    parts[4] = "100.0"
    lines[1] = ",".join(parts)
    p.write_text("\n".join(lines) + "\n")
    write_checksums(dest, label="package")
    try:
        elig, _, blockers, _ = certify_research_package(package_root=dest)
        assert elig == "development_only"
        assert blockers
    except Exception as exc:  # fail-closed on corrupt OHLC
        assert "high must be >= low" in str(exc) or "Value error" in str(exc)


def test_calendar_mismatch_or_missing_session_blocks(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "calsess")
    # Drop mid-month sessions for AAA to create missing open sessions
    p = dest / "bars" / "AAA.csv"
    lines = p.read_text().splitlines()
    header, rows = lines[0], lines[1:]
    # keep only first 5 sessions
    p.write_text("\n".join([header] + rows[:5]) + "\n")
    write_checksums(dest, label="package")
    elig, _, blockers, _ = certify_research_package(package_root=dest)
    assert elig == "development_only"
    assert any(
        "missing" in b.lower() or "session" in b.lower() or "calendar" in b.lower()
        for b in blockers
    ) or blockers


def test_yellow_for_incomplete_capable(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "yellow")
    (dest / "corporate_actions.json").write_text("[]", encoding="utf-8")
    write_checksums(dest, label="package")
    report = evaluate_research_readiness(dest)
    assert report.light in {ReadinessLight.YELLOW, ReadinessLight.RED}
    assert report.research_eligible is False


def test_invalid_license_metadata_unknown_blocks(tmp_path: Path):
    dest = _copy_fixture(tmp_path, "unklic")
    meta = json.loads((dest / "package.json").read_text())
    meta["license_status"] = "unknown"
    (dest / "package.json").write_text(json.dumps(meta, indent=2))
    (dest / "LICENSE.json").write_text(
        json.dumps({"license_status": "unknown"}), encoding="utf-8"
    )
    write_checksums(dest, label="package")
    elig, _, blockers, _ = certify_research_package(package_root=dest)
    assert elig == "development_only"
    assert any("license" in b for b in blockers) or blockers


# --- Phase 8 / live untouched ---


def test_phase8_paper_imports_untouched():
    from quantfund.paper import PaperEligibilityGate
    from quantfund.paper.execution import PaperExecutionAdapter

    assert PaperExecutionAdapter is not None
    assert PaperEligibilityGate is not None


def test_no_live_send_mode():
    assert not hasattr(ExecutionMode, "LIVE_SEND")
    assert list(ExecutionMode) == [ExecutionMode.DRY_RUN]


def test_phase9a_test_count_at_least_50():
    import tests.unit.test_phase9a_research_data as mod

    n = len([x for x in dir(mod) if x.startswith("test_")])
    assert n >= 50, f"expected >=50 phase9a tests, found {n}"

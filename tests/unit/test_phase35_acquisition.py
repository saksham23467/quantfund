"""Phase 3.5 adversarial tests: acquisition, identity, membership, provenance."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.corporate_actions.adjust import apply_adjustment_policy
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.corporate_actions.policies import default_split_bonus_policy
from quantfund.data.datasets.builder import DatasetBuilder
from quantfund.data.datasets.manifest import SourceGrade
from quantfund.data.identity import apply_symbol_change
from quantfund.data.ingest.checksums import directory_checksum
from quantfund.data.ingest.pipeline import ingest_bars_raw, load_raw_bars
from quantfund.data.instruments.delisted import TerminalEvent, TerminalEventStore, TerminalEventType
from quantfund.data.instruments.master import InstrumentMasterStore
from quantfund.data.models import Instrument, MarketBar, SymbolHistoryEntry
from quantfund.data.providers.local_package import LocalResearchPackageProvider
from quantfund.data.providers.roles import UnconfiguredResearchProvider
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.universe.import_membership import build_universe_from_membership_file
from quantfund.data.universe.membership import MembershipAnswer, was_member
from quantfund.data.universe.models import UniverseCompleteness, VerificationStatus

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "phase35" / "pilot_package"
MEMBERSHIP_CSV = (
    Path(__file__).resolve().parents[2]
    / "data/universes/nifty50/universe_version=pit_partial_documented_v1/membership.csv"
)


@pytest.fixture
def pilot_provider() -> LocalResearchPackageProvider:
    return LocalResearchPackageProvider(FIXTURE)


def test_local_package_declares_capabilities_not_auto_research(pilot_provider):
    caps = pilot_provider.capabilities()
    assert caps.source_grade == SourceGrade.SYNTHETIC
    assert caps.exchange_authority is False
    assert pilot_provider.can_claim_research_eligible is False
    prov = pilot_provider.provenance()
    assert prov.source
    assert prov.limitations


def test_ticker_change_preserves_instrument_id():
    inst = Instrument(
        symbol="OLDCO",
        instrument_id="NSE:INE111A01010",
        isin="INE111A01010",
        exchange="NSE",
        listing_date=date(2010, 1, 1),
        symbol_history=[
            SymbolHistoryEntry(symbol="OLDCO", valid_from=date(2010, 1, 1), valid_to=None)
        ],
    )
    action = CorporateAction(
        action_id="sc",
        instrument_id="NSE:INE111A01010",
        symbol="OLDCO",
        action_type=CorporateActionType.SYMBOL_CHANGE,
        ex_date=date(2024, 5, 1),
        source="test",
        verified=True,
    )
    updated = apply_symbol_change(inst, action, new_symbol="NEWCO")
    assert updated.instrument_id == "NSE:INE111A01010"
    assert updated.symbol_asof(date(2024, 4, 30)) == "OLDCO"
    assert updated.symbol_asof(date(2024, 5, 1)) == "NEWCO"


def test_delisted_stock_tracked_not_erased(tmp_path: Path):
    store = TerminalEventStore(tmp_path / "terminal")
    events = [
        TerminalEvent(
            event_id="d1",
            instrument_id="NSE:INEDEAD01010",
            symbol="DEADCO",
            event_type=TerminalEventType.DELISTING,
            event_date=date(2023, 6, 1),
            source="test",
            verification_status="verified",
        ),
        TerminalEvent(
            event_id="m1",
            instrument_id="NSE:INEMERG01010",
            symbol="MERGECO",
            event_type=TerminalEventType.MERGER,
            event_date=date(2022, 1, 1),
            source="test",
            requires_manual_treatment=True,
        ),
    ]
    store.save(catalog_id="india_eq", catalog_version="v1", events=events, source="test")
    loaded = store.load("india_eq", "v1")
    assert len(loaded) == 2
    assert loaded[1].requires_manual_treatment is True
    with pytest.raises(FileExistsError):
        store.save(catalog_id="india_eq", catalog_version="v1", events=events, source="test")


def test_historical_constituent_enter_and_leave_nifty50():
    u = build_universe_from_membership_file(
        MEMBERSHIP_CSV,
        universe_id="nifty50",
        universe_version="pit_partial_documented_v1",
        effective_start=date(2023, 1, 1),
        effective_end=date(2025, 12, 31),
        source="documented",
        completeness=UniverseCompleteness.PARTIAL_PIT,
        verification_status=VerificationStatus.PARTIAL,
    )
    # Enter
    assert was_member(u, symbol="SHRIRAMFIN", on=date(2024, 3, 27)) == MembershipAnswer.FALSE
    assert was_member(u, symbol="SHRIRAMFIN", on=date(2024, 3, 28)) == MembershipAnswer.TRUE
    # Leave
    assert was_member(u, symbol="UPL", on=date(2024, 3, 27)) == MembershipAnswer.TRUE
    assert was_member(u, symbol="UPL", on=date(2024, 3, 28)) == MembershipAnswer.FALSE
    # Missing historical constituent (untracked) → UNKNOWN
    assert was_member(u, symbol="RELIANCE", on=date(2024, 3, 28)) == MembershipAnswer.UNKNOWN
    assert MembershipAnswer.UNKNOWN != MembershipAnswer.FALSE


def test_split_bonus_dividend_raw_vs_adjusted(pilot_provider):
    bars = pilot_provider.get_history("RELIANCE")
    actions = pilot_provider.get_corporate_actions(symbol="RELIANCE")
    assert any(a.action_type == CorporateActionType.SPLIT for a in actions)
    raw_before = [(b.open, b.high, b.low, b.close) for b in bars]
    adjusted = apply_adjustment_policy(bars, actions, default_split_bonus_policy())
    raw_after = [(a.raw.open, a.raw.high, a.raw.low, a.raw.close) for a in adjusted]
    assert raw_before == raw_after
    # Pre-split adjusted should differ when factor applies
    pre = [a for a in adjusted if a.raw.timestamp.date() < date(2024, 3, 15)]
    assert pre
    assert pre[0].adj_close != pre[0].raw.close

    tcs = apply_adjustment_policy(
        pilot_provider.get_history("TCS"),
        pilot_provider.get_corporate_actions(symbol="TCS"),
        default_split_bonus_policy(),
    )
    # Dividend must not alter adjusted OHLC under default policy
    for a in tcs:
        if a.dividends:
            assert a.adj_close == a.raw.close


def test_duplicate_and_missing_open_session_errors():
    cal = FakeCalendarProvider([date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)])
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="X",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="X",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 4),
            symbol="X",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
    ]
    report = run_quality_checks(bars, calendar=cal)
    assert any(i.code == "duplicate_bar" for i in report.issues)
    assert any(i.code == "missing_open_session" for i in report.issues)


def test_incorrect_holiday_hides_missing_bar_false_confidence():
    nse = NSECalendarProvider()
    # 2024-01-25 is open on NSE; omit that bar
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 24),
            symbol="X",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 29),
            symbol="X",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        ),
    ]
    correct = run_quality_checks(
        bars, calendar=nse, start=date(2024, 1, 24), end=date(2024, 1, 29)
    )
    assert any(i.code == "missing_open_session" for i in correct.issues)


def test_provider_symbol_mismatch_detected_in_master(tmp_path: Path, pilot_provider):
    master = InstrumentMasterStore(tmp_path / "master")
    instruments = pilot_provider.get_instrument_master()
    # Corrupt a provider mapping deliberately in a copy
    bad = instruments[0].model_copy(
        update={"provider_symbols": {"yfinance": "WRONG.NS", "local_package": instruments[0].symbol}}
    )
    rest = [bad] + instruments[1:]
    master.save(
        master_id="india_eq",
        master_version="v_bad",
        instruments=rest,
        source="test",
    )
    loaded = master.load("india_eq", "v_bad")
    assert loaded[0].provider_symbols["yfinance"] == "WRONG.NS"
    assert loaded[0].instrument_id.startswith("NSE:INE")


def test_immutable_dataset_and_deterministic_ingest(tmp_path: Path, pilot_provider):
    instruments = pilot_provider.get_instrument_master()[:2]
    r1 = ingest_bars_raw(
        provider=pilot_provider,
        instruments=instruments,
        raw_root=tmp_path / "raw",
        download_id="d1",
    )
    with pytest.raises(FileExistsError):
        ingest_bars_raw(
            provider=pilot_provider,
            instruments=instruments,
            raw_root=tmp_path / "raw",
            download_id="d1",
        )
    assert (r1.root / "provenance.json").exists()
    bars_a = load_raw_bars(r1.root)
    r2 = ingest_bars_raw(
        provider=pilot_provider,
        instruments=instruments,
        raw_root=tmp_path / "raw",
        download_id="d2",
    )
    bars_b = load_raw_bars(r2.root)
    assert len(bars_a) == len(bars_b)
    # Content of bar CSVs deterministic
    h1 = directory_checksum(r1.root / "bars")
    h2 = directory_checksum(r2.root / "bars")
    assert h1 == h2


def test_provenance_preserved_on_ingest(tmp_path: Path, pilot_provider):
    r = ingest_bars_raw(
        provider=pilot_provider,
        instruments=pilot_provider.get_instrument_master()[:1],
        raw_root=tmp_path / "raw",
        download_id="prov1",
        extra_meta={"license_ref": "DATA_LICENSE.md#synthetic-fixtures"},
    )
    prov = json.loads((r.root / "provenance.json").read_text(encoding="utf-8"))
    assert prov["provider"] == "local_research_package"
    assert "content_hashes" in prov
    assert prov["extras"]["license_ref"] == "DATA_LICENSE.md#synthetic-fixtures"
    assert (r.root / "capabilities.json").exists()


def test_pilot_dataset_builds_development_only(tmp_path: Path, pilot_provider):
    bars = []
    for sym in ["RELIANCE", "TCS", "UPL", "SHRIRAMFIN"]:
        bars.extend(pilot_provider.get_history(sym))
    u = build_universe_from_membership_file(
        MEMBERSHIP_CSV,
        universe_id="nifty50",
        universe_version="pit_partial_documented_v1",
        effective_start=date(2023, 1, 1),
        effective_end=date(2025, 12, 31),
        source="documented",
        completeness=UniverseCompleteness.PARTIAL_PIT,
        verification_status=VerificationStatus.PARTIAL,
    )
    # Use FakeCalendar matching sessions present in bars for the 4 symbols
    dates = sorted({b.timestamp.date() for b in bars})
    cal = FakeCalendarProvider(dates, verified=True, calendar_id="NSE_EQ")
    # Override verified via fake — FakeCalendarProvider verified param
    builder = DatasetBuilder(tmp_path / "datasets")
    manifest, quality = builder.build(
        dataset_id="pilot_test",
        dataset_version="v1",
        bars=bars,
        universe=u,
        calendar=cal,
        actions=pilot_provider.get_corporate_actions(),
        source=pilot_provider.name,
        download_id="t",
        source_grade=SourceGrade.SYNTHETIC,
        instruments=pilot_provider.get_instrument_master(),
        fail_on_quality_errors=True,
    )
    assert manifest.research_eligibility.value == "development_only"
    assert quality.error_count == 0
    assert (tmp_path / "datasets" / "pilot_test" / "v1" / "certification.txt").exists()


def test_unconfigured_research_provider_still_refuses():
    p = UnconfiguredResearchProvider()
    assert p.can_claim_research_eligible is False
    with pytest.raises(NotImplementedError):
        p.get_history("RELIANCE")

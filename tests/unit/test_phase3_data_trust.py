"""Phase 3 adversarial / data-trust tests — catch false confidence."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.certification import certify, facts_from_manifest_and_quality
from quantfund.data.corporate_actions.adjust import apply_adjustment_policy
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.corporate_actions.policies import default_split_bonus_policy
from quantfund.data.datasets.builder import DatasetBuilder
from quantfund.data.datasets.manifest import SourceGrade
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.identity import apply_symbol_change
from quantfund.data.ingest.checksums import directory_checksum, hash_json
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.policy import (
    DatasetCertificationFacts,
    DelistedCoverage,
    EligibilityLevel,
)
from quantfund.data.providers.roles import DevelopmentProvider, UnconfiguredResearchProvider
from quantfund.data.providers.yfinance_provider import YFinanceProvider
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.universe.membership import (
    MembershipAnswer,
    build_pit_universe,
    build_stage_a_snapshot,
    detect_current_snapshot_used_as_history,
    was_member,
)
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseMembership,
    VerificationStatus,
)


def _bar(d: date, symbol: str = "AAA", close: float = 100.0, **kwargs) -> MarketBar:
    return MarketBar(
        timestamp=datetime(d.year, d.month, d.day),
        symbol=symbol,
        open=kwargs.get("open", close),
        high=kwargs.get("high", close + 1),
        low=kwargs.get("low", close - 1),
        close=close,
        volume=kwargs.get("volume", 1000),
        instrument_id=kwargs.get("instrument_id", f"NSE:{symbol}"),
    )


def test_today_constituents_as_history_rejected_for_research():
    """1. Today's constituents inserted into a historical period → rejected."""
    u = build_stage_a_snapshot(
        universe_id="nifty50",
        universe_version="today",
        as_of_date=date(2026, 8, 10),
        members=[UniverseMember(instrument_id="NSE:AAA", symbol="AAA")],
        source="today_snapshot",
    )
    assert detect_current_snapshot_used_as_history(
        u, historical_start=date(2024, 1, 2), historical_end=date(2024, 6, 1)
    )
    cal = FakeCalendarProvider([date(2024, 1, 2), date(2024, 1, 3)], verified=True)
    bars = [_bar(date(2024, 1, 2)), _bar(date(2024, 1, 3))]
    report = run_quality_checks(bars, calendar=cal, universe=u)
    assert any(i.code == "current_snapshot_used_as_history" for i in report.issues)

    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="v1",
        source="paid_vendor",
        source_grade="paid",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="nifty50",
        universe_version="today",
        universe_completeness="current_snapshot_only",
        corporate_action_coverage="splits_bonus_dividends",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-02",
        date_coverage_end="2024-01-03",
        instrument_count=1,
        content_hash="sha256:abc",
    )
    decision = ResearchEligibilityChecker().evaluate(facts)
    assert decision.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("current_snapshot_only" in b for b in decision.blockers)


def test_wrong_calendar_hides_missing_session_is_error_on_verified_nse():
    """2/3. Missing session/bar on verified open day → ERROR."""
    nse = NSECalendarProvider()
    bars = [_bar(date(2024, 1, 24)), _bar(date(2024, 1, 29))]
    report = run_quality_checks(
        bars, calendar=nse, start=date(2024, 1, 24), end=date(2024, 1, 29)
    )
    assert any(
        i.code == "missing_open_session" and i.timestamp == "2024-01-25"
        for i in report.issues
    )
    assert report.error_count >= 1
    assert report.missing_bars >= 1


def test_unknown_membership_distinct_and_no_trade_semantics():
    """4. UNKNOWN membership remains distinct from FALSE."""
    u = build_stage_a_snapshot(
        universe_id="nifty50",
        universe_version="s",
        as_of_date=date(2024, 1, 8),
        members=[UniverseMember(instrument_id="NSE:AAA", symbol="AAA")],
        source="t",
    )
    assert was_member(u, symbol="AAA", on=date(2024, 1, 2)) == MembershipAnswer.UNKNOWN
    assert was_member(u, symbol="ZZZ", on=date(2024, 1, 8)) == MembershipAnswer.FALSE
    assert MembershipAnswer.UNKNOWN != MembershipAnswer.FALSE


def test_symbol_change_keeps_instrument_identity():
    """5. Symbol change must not invent a new company."""
    inst = Instrument(
        symbol="OLDCO",
        instrument_id="NSE:INE000A01010",
        isin="INE000A01010",
        exchange="NSE",
        listing_date=date(2010, 1, 1),
    )
    action = CorporateAction(
        action_id="sc1",
        instrument_id="NSE:INE000A01010",
        symbol="OLDCO",
        action_type=CorporateActionType.SYMBOL_CHANGE,
        ex_date=date(2024, 6, 1),
        source="test",
        verified=True,
    )
    updated = apply_symbol_change(inst, action, new_symbol="NEWCO")
    assert updated.instrument_id == "NSE:INE000A01010"
    assert updated.symbol == "NEWCO"
    assert updated.symbol_asof(date(2024, 5, 31)) == "OLDCO"
    assert updated.symbol_asof(date(2024, 6, 1)) == "NEWCO"

    with pytest.raises(ValueError, match="mismatch"):
        apply_symbol_change(
            inst.model_copy(update={"instrument_id": "NSE:OTHER"}),
            action,
            new_symbol="NEWCO",
        )


def test_split_and_dividend_do_not_mutate_raw_ohlc():
    """6/7. Split/dividend must not modify RAW OHLC; adj follows policy."""
    bars = [
        _bar(date(2024, 1, 2), close=200.0, open=200.0, high=210.0, low=190.0),
        _bar(date(2024, 1, 3), close=100.0, open=100.0, high=105.0, low=95.0),
    ]
    actions = [
        CorporateAction(
            action_id="split",
            instrument_id="NSE:AAA",
            symbol="AAA",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 1, 3),
            ratio_num=2,
            ratio_den=1,
            source="t",
            verified=True,
        ),
        CorporateAction(
            action_id="div",
            instrument_id="NSE:AAA",
            symbol="AAA",
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2024, 1, 3),
            cash_amount=5.0,
            source="t",
            verified=True,
        ),
    ]
    raw_before = [(b.open, b.high, b.low, b.close) for b in bars]
    adjusted = apply_adjustment_policy(bars, actions, default_split_bonus_policy())
    raw_after = [(a.raw.open, a.raw.high, a.raw.low, a.raw.close) for a in adjusted]
    assert raw_before == raw_after
    assert adjusted[0].adj_close == pytest.approx(100.0)
    # Dividend must not change adjusted OHLC under default policy
    assert adjusted[1].adj_close == pytest.approx(adjusted[1].raw.close)
    assert adjusted[1].dividends[0].cash_amount == 5.0


def test_dataset_hash_mismatch_after_publication(tmp_path: Path):
    """8. Dataset modified after publication → hash mismatch."""
    cal = FakeCalendarProvider([date(2024, 1, 2), date(2024, 1, 3)], verified=False)
    u = build_stage_a_snapshot(
        universe_id="u",
        universe_version="v",
        as_of_date=date(2024, 1, 8),
        members=[UniverseMember(instrument_id="NSE:AAA", symbol="AAA")],
        source="t",
    )
    builder = DatasetBuilder(tmp_path / "datasets")
    manifest, _ = builder.build(
        dataset_id="hash_ds",
        dataset_version="v1",
        bars=[_bar(date(2024, 1, 2)), _bar(date(2024, 1, 3))],
        universe=u,
        calendar=cal,
        source="yfinance",
        download_id="d1",
        source_grade=SourceGrade.NON_EXCHANGE,
    )
    bars_root = tmp_path / "datasets" / "hash_ds" / "v1" / "bars"
    published = manifest.content_hash
    # Tamper
    part = next(bars_root.rglob("part.parquet"))
    part.write_bytes(part.read_bytes() + b"\x00")
    assert directory_checksum(bars_root) != published


def test_deterministic_content_hash_same_bars_twice(tmp_path: Path):
    """9. Same dataset built twice → deterministic content hash."""
    cal = FakeCalendarProvider([date(2024, 1, 2), date(2024, 1, 3)], verified=False)
    u = build_stage_a_snapshot(
        universe_id="u",
        universe_version="v",
        as_of_date=date(2024, 1, 8),
        members=[UniverseMember(instrument_id="NSE:AAA", symbol="AAA")],
        source="t",
    )
    bars = [_bar(date(2024, 1, 2)), _bar(date(2024, 1, 3))]
    b1 = DatasetBuilder(tmp_path / "d1")
    b2 = DatasetBuilder(tmp_path / "d2")
    m1, _ = b1.build(
        dataset_id="a",
        dataset_version="v1",
        bars=bars,
        universe=u,
        calendar=cal,
        source="synthetic",
        download_id="x",
        source_grade=SourceGrade.SYNTHETIC,
    )
    m2, _ = b2.build(
        dataset_id="a",
        dataset_version="v1",
        bars=bars,
        universe=u,
        calendar=cal,
        source="synthetic",
        download_id="x",
        source_grade=SourceGrade.SYNTHETIC,
    )
    assert m1.content_hash == m2.content_hash


def test_non_exchange_cannot_claim_research_grade():
    """10. Non-exchange provider attempting research-grade → rejected."""
    yf = YFinanceProvider()
    assert isinstance(yf, DevelopmentProvider)
    assert yf.source_grade == SourceGrade.NON_EXCHANGE
    assert yf.can_claim_research_eligible is False

    facts = DatasetCertificationFacts(
        dataset_id="yf",
        dataset_version="v1",
        source="yfinance",
        source_grade="non_exchange",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="nifty50",
        universe_version="pit",
        universe_completeness="partial_pit",
        corporate_action_coverage="splits_bonus_dividends",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2024-01-01",
        date_coverage_end="2024-12-31",
        instrument_count=50,
        content_hash="sha256:x",
        error_count=0,
    )
    decision = certify(facts)
    assert decision.level == EligibilityLevel.DEVELOPMENT_ONLY
    assert any("non_exchange" in b for b in decision.blockers)


def test_future_corporate_action_visible_to_raw_rejected():
    """11. Future corporate action accidentally visible → ERROR."""
    cal = FakeCalendarProvider([date(2024, 1, 2), date(2024, 1, 3)], verified=True)
    bars = [_bar(date(2024, 1, 2)), _bar(date(2024, 1, 3))]
    actions = [
        CorporateAction(
            action_id="future",
            instrument_id="NSE:AAA",
            symbol="AAA",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 2, 1),
            ratio_num=2,
            ratio_den=1,
            source="t",
        )
    ]
    report = run_quality_checks(
        bars, calendar=cal, actions=actions, asof_date=date(2024, 1, 3)
    )
    assert any(i.code == "future_corporate_action_visible" for i in report.issues)
    assert report.error_count >= 1


def test_delisted_silently_removed_from_snapshot_is_error():
    """12. Delisted instrument silently removed under Stage A → error."""
    cal = FakeCalendarProvider([date(2024, 1, 2), date(2024, 1, 3)], verified=True)
    u = build_stage_a_snapshot(
        universe_id="nifty50",
        universe_version="today",
        as_of_date=date(2024, 1, 8),
        members=[UniverseMember(instrument_id="NSE:SURV", symbol="SURV")],
        source="t",
    )
    instruments = [
        Instrument(
            symbol="DEAD",
            instrument_id="NSE:DEAD",
            exchange="NSE",
            listing_date=date(2015, 1, 1),
            delisting_date=date(2024, 1, 2),
        )
    ]
    report = run_quality_checks(
        [_bar(date(2024, 1, 2), symbol="SURV"), _bar(date(2024, 1, 3), symbol="SURV")],
        calendar=cal,
        universe=u,
        instruments=instruments,
    )
    assert any(i.code == "delisted_silently_removed" for i in report.issues)


def test_pit_membership_intervals_true_false_unknown():
    memberships = [
        UniverseMembership(
            universe_id="nifty50",
            instrument_id="NSE:AAA",
            symbol="AAA",
            member_from=date(2024, 1, 1),
            member_to=date(2024, 6, 30),
            source="index_provider",
            verification_status=VerificationStatus.VERIFIED,
        )
    ]
    u = build_pit_universe(
        universe_id="nifty50",
        universe_version="pit_v1",
        memberships=memberships,
        as_of_date=date(2024, 12, 31),
        effective_start=date(2024, 1, 1),
        effective_end=date(2024, 12, 31),
        source="index_provider",
        completeness=UniverseCompleteness.PARTIAL_PIT,
        verification_status=VerificationStatus.PARTIAL,
    )
    assert was_member(u, instrument_id="NSE:AAA", on=date(2024, 3, 1)) == MembershipAnswer.TRUE
    assert was_member(u, instrument_id="NSE:AAA", on=date(2024, 8, 1)) == MembershipAnswer.FALSE
    assert was_member(u, instrument_id="NSE:AAA", on=date(2023, 12, 1)) == MembershipAnswer.UNKNOWN


def test_metrics_cannot_promote_eligibility():
    """Good metrics must not create production_candidate."""
    facts = DatasetCertificationFacts(
        dataset_id="x",
        dataset_version="v1",
        source="yfinance",
        source_grade="non_exchange",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="nifty50",
        universe_version="pit",
        universe_completeness="full_pit",
        corporate_action_coverage="full_verified",
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start="2023-01-01",
        date_coverage_end="2025-12-31",
        instrument_count=50,
        delisted_coverage=DelistedCoverage.COMPLETE.value,
        content_hash="sha256:x",
        error_count=0,
        warning_count=0,
        extras={"sharpe": 3.5, "cagr": 0.4},
    )
    decision = ResearchEligibilityChecker().evaluate(facts)
    assert decision.level == EligibilityLevel.DEVELOPMENT_ONLY


def test_unconfigured_research_provider_refuses_fabricated_bars():
    p = UnconfiguredResearchProvider()
    with pytest.raises(NotImplementedError, match="exchange-grade"):
        p.get_history("RELIANCE")


def test_reverse_split_and_bonus_golden_raw_preserved():
    bars = [
        _bar(date(2024, 1, 2), close=50.0, open=50.0, high=51.0, low=49.0),
        _bar(date(2024, 1, 3), close=100.0, open=100.0, high=101.0, low=99.0),
    ]
    # 1-for-2 reverse split on 2024-01-03
    rev = [
        CorporateAction(
            action_id="rev",
            instrument_id="NSE:AAA",
            symbol="AAA",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 1, 3),
            ratio_num=1,
            ratio_den=2,
            source="t",
            verified=True,
        )
    ]
    adj = apply_adjustment_policy(bars, rev, default_split_bonus_policy())
    assert adj[0].raw.close == 50.0
    assert adj[0].adj_close == pytest.approx(100.0)
    assert adj[1].raw.close == 100.0

    # 3-for-2 bonus ⇒ share multiplier 1.5
    bonus = [
        CorporateAction(
            action_id="bonus",
            instrument_id="NSE:AAA",
            symbol="AAA",
            action_type=CorporateActionType.BONUS,
            ex_date=date(2024, 1, 3),
            ratio_num=3,
            ratio_den=2,
            source="t",
            verified=True,
        )
    ]
    adj_b = apply_adjustment_policy(bars, bonus, default_split_bonus_policy())
    assert adj_b[0].raw.close == 50.0
    assert adj_b[0].adj_close == pytest.approx(50.0 / 1.5)


def test_calendar_content_hash_stable():
    a = NSECalendarProvider()
    b = NSECalendarProvider(calendar_version="nse_eq_v2018_2026_r1")
    assert a.content_hash == b.content_hash
    assert a.content_hash == hash_json(
        json.loads(
            (
                Path("data/calendars/nse_eq/calendar_version=nse_eq_v2018_2026_r1")
                / "calendar.json"
            ).read_text(encoding="utf-8")
        )
    )
    # Prior version remains loadable with its own stable hash
    old = NSECalendarProvider(calendar_version="nse_eq_v2023_2025_r1")
    assert old.content_hash == hash_json(
        json.loads(
            (
                Path("data/calendars/nse_eq/calendar_version=nse_eq_v2023_2025_r1")
                / "calendar.json"
            ).read_text(encoding="utf-8")
        )
    )
    assert old.content_hash != a.content_hash


def test_builder_writes_certification(tmp_path: Path):
    cal = FakeCalendarProvider([date(2024, 1, 2), date(2024, 1, 3)], verified=False)
    u = build_stage_a_snapshot(
        universe_id="u",
        universe_version="v",
        as_of_date=date(2024, 1, 8),
        members=[UniverseMember(instrument_id="NSE:AAA", symbol="AAA")],
        source="t",
    )
    builder = DatasetBuilder(tmp_path / "datasets")
    manifest, quality = builder.build(
        dataset_id="cert",
        dataset_version="v1",
        bars=[_bar(date(2024, 1, 2)), _bar(date(2024, 1, 3))],
        universe=u,
        calendar=cal,
        source="yfinance",
        download_id="d",
        source_grade=SourceGrade.NON_EXCHANGE,
    )
    cert = tmp_path / "datasets" / "cert" / "v1" / "certification.txt"
    assert cert.exists()
    text = cert.read_text(encoding="utf-8")
    assert "RESEARCH DATASET CERTIFICATION" in text
    assert "DEVELOPMENT_ONLY" in text
    facts = facts_from_manifest_and_quality(manifest=manifest, quality=quality)
    assert certify(facts).level == EligibilityLevel.DEVELOPMENT_ONLY

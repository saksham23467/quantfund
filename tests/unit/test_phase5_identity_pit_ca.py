"""Phase 5 — identity, PIT coverage, CA coverage."""

from __future__ import annotations

from datetime import date, datetime

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.corporate_actions.coverage import (
    ActionTypeCoverage,
    derive_ca_coverage_report,
)
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.identity import (
    IDENTITY_POLICY,
    apply_symbol_change,
    check_isin_collision_registry,
    resolve_instrument_id,
)
from quantfund.data.instruments.delisted import (
    TerminalEvent,
    TerminalEventType,
    check_delisting_terminal_consistency,
    compute_delisted_coverage,
)
from quantfund.data.models import Instrument, MarketBar, SymbolHistoryEntry
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.quality.report import Severity
from quantfund.data.universe.coverage import compute_membership_coverage
from quantfund.data.universe.membership import (
    MembershipAnswer,
    UniverseMembershipStore,
    build_pit_universe,
    was_member,
)
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMembership,
    VerificationStatus,
)


def test_identity_policy_document_present():
    assert "exchange:ISIN" in IDENTITY_POLICY["permanent_id"]


def test_isin_stable_id_across_rename():
    inst = Instrument(
        symbol="OLD",
        exchange="NSE",
        isin="INE002A01018",
        listing_date=date(2020, 1, 1),
    )
    assert inst.instrument_id == "NSE:INE002A01018"
    action = CorporateAction(
        action_id="sc1",
        instrument_id=inst.instrument_id,
        symbol="OLD",
        action_type=CorporateActionType.SYMBOL_CHANGE,
        ex_date=date(2024, 3, 1),
        source="t",
        verified=True,
    )
    renamed = apply_symbol_change(inst, action, new_symbol="NEW")
    assert renamed.instrument_id == inst.instrument_id
    assert renamed.symbol == "NEW"
    assert renamed.symbol_asof(date(2024, 2, 1)) == "OLD"
    assert renamed.symbol_asof(date(2024, 3, 1)) == "NEW"


def test_resolve_instrument_id_never_ticker_alone_when_isin_known():
    assert resolve_instrument_id(exchange="NSE", isin="INE009A01021", symbol="INFY") == (
        "NSE:INE009A01021"
    )


def test_isin_collision_registry_error():
    a = Instrument(symbol="A", exchange="NSE", isin="INE000000001", instrument_id="NSE:X")
    b = Instrument(symbol="B", exchange="NSE", isin="INE000000001", instrument_id="NSE:Y")
    issues = check_isin_collision_registry([a, b])
    assert any(i.code == "isin_identity_collision" for i in issues)


def test_delisting_date_inconsistency_error():
    inst = Instrument(
        symbol="GONE",
        exchange="NSE",
        isin="INE999A01001",
        delisting_date=date(2024, 2, 1),
    )
    ev = TerminalEvent(
        event_id="t1",
        instrument_id=inst.instrument_id or "",
        symbol="GONE",
        event_type=TerminalEventType.DELISTING,
        event_date=date(2024, 3, 1),
        source="t",
    )
    issues = check_delisting_terminal_consistency([inst], [ev])
    assert any(i.code == "delisting_date_inconsistency" for i in issues)


def test_pit_reconstitution_enter_leave():
    memberships = [
        UniverseMembership(
            universe_id="nifty50",
            instrument_id="NSE:AAA",
            symbol="AAA",
            member_from=date(2024, 1, 1),
            member_to=date(2024, 3, 31),
            source="doc",
            verification_status=VerificationStatus.VERIFIED,
        ),
        UniverseMembership(
            universe_id="nifty50",
            instrument_id="NSE:BBB",
            symbol="BBB",
            member_from=date(2024, 4, 1),
            member_to=None,
            source="doc",
            verification_status=VerificationStatus.VERIFIED,
        ),
    ]
    u = build_pit_universe(
        universe_id="nifty50",
        universe_version="t",
        memberships=memberships,
        as_of_date=date(2024, 6, 1),
        effective_start=date(2024, 1, 1),
        effective_end=date(2024, 6, 30),
        source="t",
        completeness=UniverseCompleteness.PARTIAL_PIT,
    )
    assert was_member(u, instrument_id="NSE:AAA", on=date(2024, 2, 1)) == MembershipAnswer.TRUE
    assert was_member(u, instrument_id="NSE:AAA", on=date(2024, 5, 1)) == MembershipAnswer.FALSE
    assert was_member(u, instrument_id="NSE:BBB", on=date(2024, 5, 1)) == MembershipAnswer.TRUE


def test_unknown_for_untracked_under_partial_pit():
    u = build_pit_universe(
        universe_id="nifty50",
        universe_version="t",
        memberships=[
            UniverseMembership(
                universe_id="nifty50",
                instrument_id="NSE:AAA",
                symbol="AAA",
                member_from=date(2024, 1, 1),
                member_to=None,
                source="doc",
                verification_status=VerificationStatus.VERIFIED,
            )
        ],
        as_of_date=date(2024, 6, 1),
        effective_start=date(2024, 1, 1),
        effective_end=date(2024, 6, 30),
        source="t",
        completeness=UniverseCompleteness.PARTIAL_PIT,
    )
    assert was_member(u, symbol="ZZZ", on=date(2024, 2, 1)) == MembershipAnswer.UNKNOWN


def test_membership_coverage_ratio_computation():
    cal = FakeCalendarProvider(
        [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)], verified=True
    )
    u = build_pit_universe(
        universe_id="u",
        universe_version="t",
        memberships=[
            UniverseMembership(
                universe_id="u",
                instrument_id="NSE:AAA",
                symbol="AAA",
                member_from=date(2024, 1, 1),
                member_to=None,
                source="doc",
                verification_status=VerificationStatus.VERIFIED,
            )
        ],
        as_of_date=date(2024, 1, 4),
        effective_start=date(2024, 1, 1),
        effective_end=date(2024, 1, 4),
        source="t",
        completeness=UniverseCompleteness.FULL_PIT,
    )
    cov = compute_membership_coverage(
        u, calendar=cal, start=date(2024, 1, 2), end=date(2024, 1, 4), symbols=["AAA"]
    )
    assert cov.unknown_membership_sessions == 0
    assert cov.membership_coverage_ratio == 1.0
    assert cov.known_membership_sessions == 3


def test_no_backward_projection_of_snapshot():
    from quantfund.data.universe.membership import build_stage_a_snapshot
    from quantfund.data.universe.models import UniverseMember

    u = build_stage_a_snapshot(
        universe_id="nifty50",
        universe_version="today",
        as_of_date=date(2024, 6, 1),
        members=[UniverseMember(instrument_id="NSE:A", symbol="A")],
        source="t",
    )
    assert was_member(u, symbol="A", on=date(2024, 1, 2)) == MembershipAnswer.UNKNOWN


def test_membership_store_immutable(tmp_path):
    store = UniverseMembershipStore(tmp_path)
    u = build_pit_universe(
        universe_id="u",
        universe_version="v1",
        memberships=[],
        as_of_date=date(2024, 1, 1),
        effective_start=date(2024, 1, 1),
        effective_end=date(2024, 1, 31),
        source="t",
    )
    store.save(u)
    import pytest

    with pytest.raises(FileExistsError):
        store.save(u)


def test_ca_split_bonus_dividend_coverage():
    actions = [
        CorporateAction(
            action_id="s",
            instrument_id="NSE:A",
            symbol="A",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 2, 1),
            ratio_num=2,
            ratio_den=1,
            source="t",
            verified=True,
        ),
        CorporateAction(
            action_id="b",
            instrument_id="NSE:A",
            symbol="A",
            action_type=CorporateActionType.BONUS,
            ex_date=date(2024, 3, 1),
            ratio_num=1,
            ratio_den=1,
            source="t",
            verified=True,
        ),
        CorporateAction(
            action_id="d",
            instrument_id="NSE:A",
            symbol="A",
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2024, 4, 1),
            cash_amount=1.0,
            source="t",
            verified=True,
        ),
    ]
    report = derive_ca_coverage_report(actions, source_grade="paid")
    assert report.splits == ActionTypeCoverage.FULL_VERIFIED
    assert report.overall == "full_verified"


def test_merger_manual_review_required():
    actions = [
        CorporateAction(
            action_id="m",
            instrument_id="NSE:A",
            symbol="A",
            action_type=CorporateActionType.MERGER,
            ex_date=date(2024, 2, 1),
            source="t",
            verified=False,
        )
    ]
    report = derive_ca_coverage_report(actions, source_grade="paid")
    assert report.mergers == ActionTypeCoverage.MANUAL_REVIEW_REQUIRED
    assert any("manual" in n.lower() for n in report.notes)


def test_synthetic_cannot_claim_full_verified_ca():
    actions = [
        CorporateAction(
            action_id="s",
            instrument_id="NSE:A",
            symbol="A",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 2, 1),
            ratio_num=2,
            ratio_den=1,
            source="t",
            verified=True,
        ),
        CorporateAction(
            action_id="b",
            instrument_id="NSE:A",
            symbol="A",
            action_type=CorporateActionType.BONUS,
            ex_date=date(2024, 3, 1),
            ratio_num=1,
            ratio_den=1,
            source="t",
            verified=True,
        ),
        CorporateAction(
            action_id="d",
            instrument_id="NSE:A",
            symbol="A",
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2024, 4, 1),
            cash_amount=1.0,
            source="t",
            verified=True,
        ),
    ]
    report = derive_ca_coverage_report(actions, source_grade="synthetic")
    assert report.overall == "splits_bonus_dividends"


def test_future_ca_visible_error():
    cal = FakeCalendarProvider([date(2024, 1, 2)], verified=True)
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="A",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
    ]
    actions = [
        CorporateAction(
            action_id="d",
            instrument_id="NSE:A",
            symbol="A",
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2024, 2, 1),
            cash_amount=1.0,
            source="t",
        )
    ]
    report = run_quality_checks(
        bars, calendar=cal, actions=actions, asof_date=date(2024, 1, 2)
    )
    assert any(i.code == "future_corporate_action_visible" for i in report.issues)


def test_delisted_coverage_none_partial():
    assert (
        compute_delisted_coverage(instruments=[], events=None)
        == "none"
    )
    inst = Instrument(
        symbol="G",
        exchange="NSE",
        isin="INE111A01001",
        delisting_date=date(2024, 1, 15),
    )
    ev = TerminalEvent(
        event_id="e",
        instrument_id=inst.instrument_id or "",
        symbol="G",
        event_type=TerminalEventType.DELISTING,
        event_date=date(2024, 1, 15),
        source="t",
        verification_status="unverified",
    )
    assert compute_delisted_coverage(instruments=[inst], events=[ev]) == "partial"

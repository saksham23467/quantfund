"""Phase 7 — PIT universe, corporate actions, market quality tests."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from quantfund.data.calendar.nse import NSECalendarProvider
from quantfund.data.corporate_actions.coverage import derive_ca_coverage_report
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.quality.report import Severity
from quantfund.data.universe.coverage import compute_membership_coverage
from quantfund.data.universe.import_membership import build_universe_from_membership_file
from quantfund.data.universe.membership import build_pit_universe, was_member, MembershipAnswer
from quantfund.data.universe.membership_audit import audit_membership_intervals
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMembership,
    VerificationStatus,
)


def _mem(
    iid: str,
    symbol: str,
    start: date,
    end: date | None,
    *,
    source: str = "doc",
) -> UniverseMembership:
    return UniverseMembership(
        universe_id="nifty50",
        instrument_id=iid,
        symbol=symbol,
        member_from=start,
        member_to=end,
        source=source,
        verification_status=VerificationStatus.VERIFIED,
        metadata={"evidence_reference": "nse_indices_archive_v1"},
    )


def test_pit_full_coverage_ratio_one():
    cal = NSECalendarProvider()
    memberships = [
        _mem("NSE:A", "AAA", date(2024, 1, 2), date(2024, 6, 28)),
    ]
    u = build_pit_universe(
        universe_id="nifty50",
        universe_version="full_t",
        memberships=memberships,
        as_of_date=date(2024, 6, 28),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 6, 28),
        source="t",
        completeness=UniverseCompleteness.FULL_PIT,
    )
    cov = compute_membership_coverage(
        u,
        calendar=cal,
        start=date(2024, 1, 2),
        end=date(2024, 6, 28),
        symbols=["AAA"],
    )
    assert cov.unknown_membership_sessions == 0
    assert cov.membership_coverage_ratio == 1.0


def test_pit_partial_unknown_sessions():
    cal = NSECalendarProvider()
    memberships = [
        _mem("NSE:A", "AAA", date(2024, 3, 1), date(2024, 3, 31)),
    ]
    u = build_pit_universe(
        universe_id="nifty50",
        universe_version="partial_t",
        memberships=memberships,
        as_of_date=date(2024, 6, 28),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 6, 28),
        source="t",
        completeness=UniverseCompleteness.PARTIAL_PIT,
    )
    # Untracked name under partial_pit → UNKNOWN (never invent FALSE)
    cov = compute_membership_coverage(
        u,
        calendar=cal,
        start=date(2024, 1, 2),
        end=date(2024, 6, 28),
        symbols=["UNTRACKED"],
        instrument_ids=["NSE:UNTRACKED"],
    )
    assert cov.unknown_membership_sessions > 0
    assert cov.membership_coverage_ratio < 1.0


def test_unknown_membership_preserved():
    u = build_pit_universe(
        universe_id="nifty50",
        universe_version="t",
        memberships=[_mem("NSE:A", "AAA", date(2024, 1, 2), date(2024, 1, 31))],
        as_of_date=date(2024, 6, 1),
        effective_start=date(2024, 1, 2),
        effective_end=date(2024, 6, 28),
        source="t",
        completeness=UniverseCompleteness.PARTIAL_PIT,
    )
    assert was_member(u, instrument_id="NSE:ZZZ", on=date(2024, 2, 1)) == MembershipAnswer.UNKNOWN


def test_membership_overlap_detected():
    rows = [
        _mem("NSE:A", "AAA", date(2024, 1, 1), date(2024, 3, 31)),
        _mem("NSE:A", "AAA", date(2024, 3, 1), date(2024, 6, 30)),
    ]
    audit = audit_membership_intervals(rows)
    assert audit.overlap_count >= 1
    assert not audit.ok


def test_membership_gap_detected():
    rows = [
        _mem("NSE:A", "AAA", date(2024, 1, 1), date(2024, 1, 31)),
        _mem("NSE:A", "AAA", date(2024, 3, 1), date(2024, 3, 31)),
    ]
    audit = audit_membership_intervals(rows)
    assert audit.gap_count >= 1


def test_duplicate_membership_detected():
    row = _mem("NSE:A", "AAA", date(2024, 1, 1), date(2024, 1, 31))
    audit = audit_membership_intervals([row, row])
    assert audit.duplicate_count == 1


def test_import_membership_rejects_overlaps(tmp_path: Path):
    path = tmp_path / "m.csv"
    path.write_text(
        "instrument_id,symbol,member_from,member_to,source,verification_status,evidence_reference\n"
        "NSE:A,AAA,2024-01-01,2024-03-31,doc,verified,ref1\n"
        "NSE:A,AAA,2024-03-01,2024-06-30,doc,verified,ref2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="overlap"):
        build_universe_from_membership_file(
            path,
            universe_id="nifty50",
            universe_version="bad",
            as_of_date=date(2024, 6, 30),
            effective_start=date(2024, 1, 1),
            effective_end=date(2024, 6, 30),
            source="t",
            completeness=UniverseCompleteness.PARTIAL_PIT,
        )


def test_ca_split_bonus_dividend_coverage():
    actions = [
        CorporateAction(
            action_id="s1",
            instrument_id="NSE:A",
            symbol="AAA",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 2, 1),
            ratio_num=2,
            ratio_den=1,
            source="t",
            verified=True,
        ),
        CorporateAction(
            action_id="b1",
            instrument_id="NSE:A",
            symbol="AAA",
            action_type=CorporateActionType.BONUS,
            ex_date=date(2024, 3, 1),
            ratio_num=1,
            ratio_den=1,
            source="t",
            verified=True,
        ),
        CorporateAction(
            action_id="d1",
            instrument_id="NSE:A",
            symbol="AAA",
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2024, 4, 1),
            cash_amount=10.0,
            source="t",
            verified=True,
        ),
        CorporateAction(
            action_id="sc1",
            instrument_id="NSE:A",
            symbol="AAA",
            action_type=CorporateActionType.SYMBOL_CHANGE,
            ex_date=date(2024, 5, 1),
            source="t",
            verified=True,
        ),
        CorporateAction(
            action_id="m1",
            instrument_id="NSE:A",
            symbol="AAA",
            action_type=CorporateActionType.MERGER,
            ex_date=date(2024, 6, 1),
            source="t",
            verified=False,
            requires_manual_treatment=True,
        ),
        CorporateAction(
            action_id="dm1",
            instrument_id="NSE:A",
            symbol="AAA",
            action_type=CorporateActionType.DEMERGER,
            ex_date=date(2024, 6, 15),
            source="t",
            verified=False,
            requires_manual_treatment=True,
        ),
    ]
    report = derive_ca_coverage_report(actions, source_grade="exchange")
    d = report.to_dict()
    assert d["split_coverage"] == "full_verified"
    assert d["bonus_coverage"] == "full_verified"
    assert d["dividend_coverage"] == "full_verified"
    assert d["identity_event_coverage"] == "full_verified"
    assert d["merger_coverage"] in {"manual_review_required", "unsupported"}
    assert d["demerger_coverage"] in {"manual_review_required", "unsupported"}


def test_rights_action_type_supported():
    a = CorporateAction(
        action_id="r1",
        instrument_id="NSE:A",
        symbol="AAA",
        action_type=CorporateActionType.RIGHTS,
        ex_date=date(2024, 2, 1),
        ratio_num=3,
        ratio_den=2,
        source="t",
        verified=True,
    )
    assert a.action_type == CorporateActionType.RIGHTS


def _bar(sym: str, d: date, o: float, h: float, l: float, c: float, v: float = 1000) -> MarketBar:
    return MarketBar(
        timestamp=datetime(d.year, d.month, d.day, 15, 30, tzinfo=timezone.utc),
        symbol=sym,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
    )


def test_duplicate_bars_error():
    cal = NSECalendarProvider()
    d = date(2024, 1, 2)
    bars = [_bar("AAA", d, 10, 11, 9, 10.5), _bar("AAA", d, 10, 11, 9, 10.5)]
    report = run_quality_checks(
        bars,
        calendar=cal,
        start=d,
        end=d,
        dataset_id="t",
        source="t",
    )
    assert report.duplicate_bars >= 1
    assert any(i.code == "duplicate_bar" for i in report.issues)


def test_bad_ohlc_caught_at_model():
    with pytest.raises(ValueError):
        _bar("AAA", date(2024, 1, 2), 10, 9, 11, 10)  # high < low


def test_extreme_discontinuity_warning():
    cal = NSECalendarProvider()
    # Two consecutive sessions with huge gap, no CA
    bars = [
        _bar("AAA", date(2024, 1, 2), 100, 101, 99, 100),
        _bar("AAA", date(2024, 1, 3), 10, 11, 9, 10),
    ]
    report = run_quality_checks(
        bars,
        calendar=cal,
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        dataset_id="t",
        source="t",
    )
    assert any(i.code == "extreme_discontinuity" for i in report.issues)


def test_ca_consistent_discontinuity_info():
    cal = NSECalendarProvider()
    actions = [
        CorporateAction(
            action_id="s1",
            instrument_id="NSE:A",
            symbol="AAA",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 1, 3),
            ratio_num=10,
            ratio_den=1,
            source="t",
            verified=True,
        )
    ]
    bars = [
        _bar("AAA", date(2024, 1, 2), 100, 101, 99, 100),
        _bar("AAA", date(2024, 1, 3), 10, 11, 9, 10),
    ]
    report = run_quality_checks(
        bars,
        calendar=cal,
        actions=actions,
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        dataset_id="t",
        source="t",
    )
    assert any(i.code == "ca_consistent_discontinuity" for i in report.issues)
    assert all(
        i.severity == Severity.INFO
        for i in report.issues
        if i.code == "ca_consistent_discontinuity"
    )


def test_stale_price_warning():
    cal = NSECalendarProvider()
    # Build many unchanged sessions on open calendar days
    sessions = []
    d = date(2024, 1, 2)
    while len(sessions) < 6:
        if cal.is_session(d):
            sessions.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    bars = [_bar("AAA", s, 50, 50, 50, 50) for s in sessions]
    report = run_quality_checks(
        bars,
        calendar=cal,
        start=sessions[0],
        end=sessions[-1],
        dataset_id="t",
        source="t",
        stale_unchanged_sessions=5,
    )
    assert report.stale_prices >= 1 or any(i.code == "stale_price" for i in report.issues)

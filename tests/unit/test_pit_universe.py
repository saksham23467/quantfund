"""Regression tests for the PIT historical universe layer.

Focus areas mandated by the task:
- Survivorship-bias prevention: a delisted-but-then-member security is still a
  member on dates it was in the index.
- Pre-membership prevention: a security cannot appear in a historical universe
  before its actual membership date.
- Fail-closed UNKNOWN semantics (never invented TRUE / never silent FALSE).
- Stable identity binding + fail-closed research eligibility.
- Corporate actions stay out of this layer (membership + identity only).
"""

from __future__ import annotations

from datetime import date

import pytest

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.instruments.delisted import TerminalEvent, TerminalEventType
from quantfund.data.models import Instrument
from quantfund.data.universe.membership import MembershipAnswer, build_pit_universe
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseMembership,
    UniverseVersion,
    VerificationStatus,
)
from quantfund.research.universe import (
    IdentityGrade,
    bind_identity,
    evaluate_research_universe_coverage,
    resolve_pit_universe,
)

UNIVERSE_ID = "test_index"


def _membership(
    instrument_id: str,
    symbol: str,
    member_from: date,
    member_to: date | None,
    *,
    status: VerificationStatus = VerificationStatus.VERIFIED,
) -> UniverseMembership:
    return UniverseMembership(
        universe_id=UNIVERSE_ID,
        instrument_id=instrument_id,
        symbol=symbol,
        member_from=member_from,
        member_to=member_to,
        source="test_ledger",
        verification_status=status,
    )


def _pit_universe(memberships: list[UniverseMembership]) -> UniverseVersion:
    return build_pit_universe(
        universe_id=UNIVERSE_ID,
        universe_version="v1",
        memberships=memberships,
        as_of_date=date(2024, 12, 31),
        effective_start=date(2020, 1, 1),
        effective_end=date(2024, 12, 31),
        source="test_ledger",
        completeness=UniverseCompleteness.FULL_PIT,
        verification_status=VerificationStatus.VERIFIED,
    )


def _instrument(
    instrument_id: str,
    symbol: str,
    *,
    isin: str | None = None,
    exchange: str = "NSE",
    delisting_date: date | None = None,
) -> Instrument:
    return Instrument(
        symbol=symbol,
        instrument_id=instrument_id,
        isin=isin,
        exchange=exchange,
        delisting_date=delisting_date,
        status="delisted" if delisting_date else "active",
    )


# --------------------------------------------------------------------------
# Pre-membership prevention
# --------------------------------------------------------------------------


def test_stock_cannot_appear_before_membership_date():
    """A stock added on 2022-06-01 must NOT be a member on 2022-05-31."""
    memberships = [
        _membership("NSE:INE_NEW", "NEWCO", date(2022, 6, 1), None),
    ]
    universe = _pit_universe(memberships)

    before = resolve_pit_universe(universe, as_of=date(2022, 5, 31))
    on_day = resolve_pit_universe(universe, as_of=date(2022, 6, 1))
    after = resolve_pit_universe(universe, as_of=date(2023, 1, 1))

    assert "NEWCO" not in before.member_symbols
    assert "NEWCO" in on_day.member_symbols
    assert "NEWCO" in after.member_symbols
    # Inside coverage, before its interval, a tracked FULL_PIT roster is FALSE
    # (known-not-member) — never fabricated TRUE.
    excluded_syms = {m.symbol for m in before.excluded}
    assert "NEWCO" in excluded_syms


def test_pre_membership_is_false_not_unknown_in_full_pit_coverage():
    memberships = [_membership("NSE:INE_NEW", "NEWCO", date(2022, 6, 1), None)]
    universe = _pit_universe(memberships)
    ans = _answer(universe, "NEWCO", date(2022, 5, 31))
    assert ans == MembershipAnswer.FALSE


def test_before_coverage_window_is_unknown_never_false():
    """Before the ledger's coverage window, membership must be UNKNOWN."""
    memberships = [_membership("NSE:INE_NEW", "NEWCO", date(2022, 6, 1), None)]
    universe = _pit_universe(memberships)  # coverage starts 2020-01-01
    ans = _answer(universe, "NEWCO", date(2019, 1, 1))
    assert ans == MembershipAnswer.UNKNOWN


# --------------------------------------------------------------------------
# Survivorship-bias prevention
# --------------------------------------------------------------------------


def test_delisted_member_still_present_on_historical_membership_dates():
    """A company that was a member then delisted must appear in the historical
    universe on dates it was a member (survivorship-bias prevention)."""
    memberships = [
        _membership("NSE:INE_DEAD", "DEADCO", date(2020, 1, 1), date(2022, 3, 15)),
        _membership("NSE:INE_LIVE", "LIVECO", date(2020, 1, 1), None),
    ]
    universe = _pit_universe(memberships)
    instruments = {
        "NSE:INE_DEAD": _instrument(
            "NSE:INE_DEAD", "DEADCO", isin="INE_DEAD", delisting_date=date(2022, 3, 15)
        ),
        "NSE:INE_LIVE": _instrument("NSE:INE_LIVE", "LIVECO", isin="INE_LIVE"),
    }

    during = resolve_pit_universe(
        universe, as_of=date(2021, 6, 1), instruments=instruments
    )
    assert "DEADCO" in during.member_symbols
    dead = next(m for m in during.members if m.symbol == "DEADCO")
    assert dead.delisted is True
    assert dead.delisting_date == date(2022, 3, 15)


def test_delisted_member_not_returned_after_delisting():
    memberships = [
        _membership("NSE:INE_DEAD", "DEADCO", date(2020, 1, 1), date(2022, 3, 15)),
    ]
    universe = _pit_universe(memberships)
    after = resolve_pit_universe(universe, as_of=date(2023, 1, 1))
    assert "DEADCO" not in after.member_symbols
    assert _answer(universe, "DEADCO", date(2023, 1, 1)) == MembershipAnswer.FALSE


def test_today_universe_not_used_for_history_snapshot_only():
    """A current_snapshot_only universe must never answer historical dates from
    today's roster — those are UNKNOWN."""
    snapshot = UniverseVersion(
        universe_id=UNIVERSE_ID,
        universe_version="snap_v1",
        completeness=UniverseCompleteness.CURRENT_SNAPSHOT_ONLY,
        as_of_date=date(2024, 12, 31),
        effective_start=date(2024, 12, 31),
        effective_end=date(2024, 12, 31),
        source="today_snapshot",
        members=[UniverseMember(instrument_id="NSE:INE_A", symbol="AAA")],
    )
    hist = resolve_pit_universe(snapshot, as_of=date(2021, 1, 1))
    assert "AAA" not in hist.member_symbols
    assert "AAA" in {m.symbol for m in hist.unknown}
    assert any("current_snapshot" in w for w in hist.warnings)


# --------------------------------------------------------------------------
# UNKNOWN semantics
# --------------------------------------------------------------------------


def test_partial_pit_absent_instrument_is_unknown_not_false():
    memberships = [
        _membership(
            "NSE:INE_A", "AAA", date(2020, 1, 1), None, status=VerificationStatus.VERIFIED
        ),
    ]
    universe = build_pit_universe(
        universe_id=UNIVERSE_ID,
        universe_version="v1",
        memberships=memberships,
        as_of_date=date(2024, 12, 31),
        effective_start=date(2020, 1, 1),
        effective_end=date(2024, 12, 31),
        source="test_ledger",
        completeness=UniverseCompleteness.PARTIAL_PIT,
        verification_status=VerificationStatus.PARTIAL,
    )
    # An instrument absent from a PARTIAL roster is UNKNOWN, never invented FALSE.
    ans = _answer(universe, "ZZZ", date(2021, 1, 1))
    assert ans == MembershipAnswer.UNKNOWN


# --------------------------------------------------------------------------
# Stable identity binding
# --------------------------------------------------------------------------


def test_identity_authoritative_when_isin_present():
    inst = _instrument("NSE:INE002A01018", "RELIANCE", isin="INE002A01018")
    binding = bind_identity(inst)
    assert binding.grade == IdentityGrade.AUTHORITATIVE_ISIN
    assert binding.is_authoritative is True
    assert binding.issues == []


def test_identity_broker_resolved_when_isin_missing():
    inst = _instrument("NSE:RELIANCE", "RELIANCE", isin=None)
    binding = bind_identity(inst)
    assert binding.grade == IdentityGrade.BROKER_RESOLVED
    assert binding.is_authoritative is False
    assert "no_isin_stable_identity" in binding.issues


def test_identity_unknown_when_no_exchange_or_isin():
    inst = Instrument(symbol="MYSTERY", instrument_id=None, exchange=None)
    binding = bind_identity(inst)
    assert binding.grade == IdentityGrade.UNKNOWN
    assert "no_stable_identity" in binding.issues


# --------------------------------------------------------------------------
# Coverage + fail-closed eligibility
# --------------------------------------------------------------------------


def _calendar(days: list[date]) -> FakeCalendarProvider:
    return FakeCalendarProvider(days)


def _sessions(start: date, count: int) -> list[date]:
    from datetime import timedelta

    return [start + timedelta(days=i) for i in range(count)]


def test_coverage_research_grade_when_fully_verified():
    days = _sessions(date(2021, 1, 4), 5)
    memberships = [
        _membership("NSE:INE_A", "AAA", date(2020, 1, 1), None),
        _membership("NSE:INE_B", "BBB", date(2020, 1, 1), date(2022, 3, 15)),
    ]
    universe = _pit_universe(memberships)
    instruments = {
        "NSE:INE_A": _instrument("NSE:INE_A", "AAA", isin="INE_A"),
        "NSE:INE_B": _instrument(
            "NSE:INE_B", "BBB", isin="INE_B", delisting_date=date(2022, 3, 15)
        ),
    }
    events = [
        TerminalEvent(
            event_id="ev1",
            instrument_id="NSE:INE_B",
            symbol="BBB",
            event_type=TerminalEventType.DELISTING,
            event_date=date(2022, 3, 15),
            source="test_ledger",
            verification_status="verified",
        )
    ]
    cov = evaluate_research_universe_coverage(
        universe,
        calendar=_calendar(days),
        start=days[0],
        end=days[-1],
        instruments=instruments,
        terminal_events=events,
    )
    assert cov.membership_coverage_ratio == 1.0
    assert cov.unknown_membership_count == 0
    assert cov.instrument_identity_coverage == 1.0
    assert cov.delisted_coverage == "complete"
    assert cov.research_eligibility is True
    assert cov.blockers == []


def test_coverage_fails_closed_without_isin():
    days = _sessions(date(2021, 1, 4), 5)
    memberships = [_membership("NSE:INE_A", "AAA", date(2020, 1, 1), None)]
    universe = _pit_universe(memberships)
    instruments = {"NSE:INE_A": _instrument("NSE:INE_A", "AAA", isin=None)}
    cov = evaluate_research_universe_coverage(
        universe,
        calendar=_calendar(days),
        start=days[0],
        end=days[-1],
        instruments=instruments,
    )
    assert cov.instrument_identity_coverage == 0.0
    assert cov.research_eligibility is False
    assert "instrument_identity_coverage_below_1.0" in cov.blockers


def test_coverage_fails_closed_on_snapshot_only_universe():
    days = _sessions(date(2021, 1, 4), 5)
    snapshot = UniverseVersion(
        universe_id=UNIVERSE_ID,
        universe_version="snap_v1",
        completeness=UniverseCompleteness.CURRENT_SNAPSHOT_ONLY,
        as_of_date=date(2024, 12, 31),
        effective_start=date(2024, 12, 31),
        effective_end=date(2024, 12, 31),
        source="today_snapshot",
        members=[UniverseMember(instrument_id="NSE:INE_A", symbol="AAA")],
    )
    instruments = {
        "NSE:INE_A": _instrument("NSE:INE_A", "AAA", isin="INE_A")
    }
    cov = evaluate_research_universe_coverage(
        snapshot,
        calendar=_calendar(days),
        start=days[0],
        end=days[-1],
        instruments=instruments,
    )
    assert cov.research_eligibility is False
    assert "universe_not_point_in_time" in cov.blockers
    assert "current_snapshot_used_as_history" in cov.blockers
    assert cov.unknown_membership_count > 0


def test_empty_instruments_fails_closed():
    days = _sessions(date(2021, 1, 4), 5)
    memberships = [_membership("NSE:INE_A", "AAA", date(2020, 1, 1), None)]
    universe = _pit_universe(memberships)
    cov = evaluate_research_universe_coverage(
        universe,
        calendar=_calendar(days),
        start=days[0],
        end=days[-1],
        instruments={},
    )
    assert cov.instrument_identity_coverage == 0.0
    assert cov.research_eligibility is False
    assert "no_instrument_identity_records" in cov.blockers


# --------------------------------------------------------------------------
# Report runner honesty (real repo state)
# --------------------------------------------------------------------------


def test_report_fails_closed_when_no_membership_ledger(tmp_path):
    """With no authoritative membership ledger, the report must fail closed."""
    from quantfund.research.universe.report import build_pit_universe_report

    payload = build_pit_universe_report(
        root=tmp_path / "does_not_exist",
        ledger_root=tmp_path / "no_ledger",
    )
    assert payload["research_eligibility"] is False
    assert payload["trading_enabled"] is False
    assert "missing_pit_membership_ledger" in payload["blockers"]
    assert payload["membership_coverage_ratio"] == 0.0


def _answer(universe: UniverseVersion, symbol: str, on: date) -> MembershipAnswer:
    from quantfund.data.universe.membership import was_member

    return was_member(universe, symbol=symbol, on=on)

"""Universe Stage A membership tests."""

from __future__ import annotations

from datetime import date

from quantfund.data.universe.membership import MembershipAnswer, was_member
from quantfund.data.universe.models import (
    SURVIVORSHIP_WARNING,
    UniverseCompleteness,
    UniverseMember,
    UniverseVersion,
)


def _stage_a() -> UniverseVersion:
    return UniverseVersion(
        universe_id="nifty50",
        universe_version="stage_a_test",
        completeness=UniverseCompleteness.CURRENT_SNAPSHOT_ONLY,
        as_of_date=date(2024, 1, 8),
        source="test",
        members=[
            UniverseMember(instrument_id="NSE:TEST", symbol="TEST"),
            UniverseMember(instrument_id="NSE:RELIANCE", symbol="RELIANCE"),
        ],
    )


def test_current_snapshot_marked_incomplete():
    u = _stage_a()
    assert u.completeness == UniverseCompleteness.CURRENT_SNAPSHOT_ONLY
    assert SURVIVORSHIP_WARNING in u.warnings


def test_membership_true_false_on_as_of_date():
    u = _stage_a()
    assert was_member(u, symbol="TEST", on=date(2024, 1, 8)) == MembershipAnswer.TRUE
    assert was_member(u, symbol="UNKNOWN", on=date(2024, 1, 8)) == MembershipAnswer.FALSE


def test_membership_unknown_for_other_dates():
    u = _stage_a()
    assert was_member(u, symbol="TEST", on=date(2020, 1, 2)) == MembershipAnswer.UNKNOWN
    assert was_member(u, symbol="TEST", on=date(2024, 1, 7)) == MembershipAnswer.UNKNOWN

"""Chronological splits and TEST isolation."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from quantfund.data.models import MarketBar
from quantfund.research.splits import (
    ChronologicalSplit,
    Period,
    SealedTestSetError,
    SplitConfig,
)


def _bars() -> list[MarketBar]:
    out = []
    for d in range(2, 12):
        c = 100 + d
        out.append(
            MarketBar(
                timestamp=datetime(2024, 1, d),
                symbol="TEST",
                open=100,
                high=c + 1,
                low=99,
                close=c,
                volume=1,
            )
        )
    return out


def test_chronological_split_non_overlapping():
    cfg = SplitConfig(
        train=Period(start=date(2024, 1, 2), end=date(2024, 1, 4)),
        validation=Period(start=date(2024, 1, 5), end=date(2024, 1, 7)),
        test=Period(start=date(2024, 1, 8), end=date(2024, 1, 11)),
    )
    split = ChronologicalSplit.from_bars(_bars(), cfg)
    assert {b.timestamp.date() for b in split.train_bars} == {
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
    }
    assert date(2024, 1, 8) in {b.timestamp.date() for b in split.test_bars}


def test_test_sealed_during_development():
    cfg = SplitConfig(
        train=Period(start=date(2024, 1, 2), end=date(2024, 1, 4)),
        validation=Period(start=date(2024, 1, 5), end=date(2024, 1, 7)),
        test=Period(start=date(2024, 1, 8), end=date(2024, 1, 11)),
    )
    split = ChronologicalSplit.from_bars(_bars(), cfg)
    with pytest.raises(SealedTestSetError):
        split.get_test_bars()
    with pytest.raises(SealedTestSetError):
        split.unlock_test(sealed_evaluation=False)
    split.unlock_test(sealed_evaluation=True)
    assert len(split.get_test_bars()) > 0


def test_overlapping_split_rejected():
    with pytest.raises(ValueError):
        SplitConfig(
            train=Period(start=date(2024, 1, 2), end=date(2024, 1, 6)),
            validation=Period(start=date(2024, 1, 5), end=date(2024, 1, 7)),
            test=Period(start=date(2024, 1, 8), end=date(2024, 1, 11)),
        )

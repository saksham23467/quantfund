"""Corporate action and adjustment policy tests."""

from __future__ import annotations

from datetime import date, datetime

from quantfund.data.corporate_actions.adjust import apply_adjustment_policy
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.corporate_actions.policies import default_split_bonus_policy
from quantfund.data.models import MarketBar


def _bars() -> list[MarketBar]:
    # Pre-split prices ~200; post 2-for-1 ~100
    return [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=200,
            high=210,
            low=190,
            close=200,
            volume=100,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 3),
            symbol="TEST",
            open=100,
            high=105,
            low=95,
            close=100,
            volume=200,
        ),
    ]


def test_split_does_not_modify_raw_ohlc():
    bars = _bars()
    raw_close_before = [b.close for b in bars]
    actions = [
        CorporateAction(
            action_id="split1",
            instrument_id="NSE:TEST",
            symbol="TEST",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 1, 3),
            ratio_num=2,
            ratio_den=1,
            source="test",
            verified=True,
        )
    ]
    adjusted = apply_adjustment_policy(bars, actions, default_split_bonus_policy())
    assert [b.close for b in bars] == raw_close_before
    assert adjusted[0].raw.close == 200
    # Before ex-date, factor includes the upcoming 2-for-1 ⇒ adj = 200/2 = 100
    assert adjusted[0].adj_close == 100
    assert adjusted[0].adjustment_factor == 2.0
    assert adjusted[1].adj_close == 100
    assert adjusted[1].adjustment_factor == 1.0


def test_bonus_does_not_modify_raw_ohlc():
    bars = _bars()
    actions = [
        CorporateAction(
            action_id="bonus1",
            instrument_id="NSE:TEST",
            symbol="TEST",
            action_type=CorporateActionType.BONUS,
            ex_date=date(2024, 1, 3),
            ratio_num=3,
            ratio_den=2,  # 3-for-2 bonus ⇒ factor 1.5
            source="test",
            verified=True,
        )
    ]
    adjusted = apply_adjustment_policy(bars, actions, default_split_bonus_policy())
    assert adjusted[0].raw.open == 200
    assert adjusted[0].adj_open == 200 / 1.5


def test_dividends_tracked_separately_not_in_ohlc_adjustment():
    bars = _bars()
    actions = [
        CorporateAction(
            action_id="div1",
            instrument_id="NSE:TEST",
            symbol="TEST",
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2024, 1, 3),
            cash_amount=5.0,
            source="test",
            verified=True,
        )
    ]
    policy = default_split_bonus_policy()
    assert policy.adjust_dividends_in_ohlc is False
    adjusted = apply_adjustment_policy(bars, actions, policy)
    # No split/bonus ⇒ factor 1; dividend attached on ex-date bar
    assert adjusted[0].adj_close == adjusted[0].raw.close
    assert adjusted[1].dividends[0].cash_amount == 5.0


def test_merger_requires_manual_treatment():
    action = CorporateAction(
        action_id="m1",
        instrument_id="NSE:TEST",
        symbol="TEST",
        action_type=CorporateActionType.MERGER,
        ex_date=date(2024, 1, 3),
        source="test",
    )
    assert action.requires_manual_treatment is True


def test_two_for_one_split_factor_consistency():
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=200,
            high=210,
            low=190,
            close=200,
            volume=100,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 3),
            symbol="TEST",
            open=100,
            high=105,
            low=95,
            close=100,
            volume=200,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 4),
            symbol="TEST",
            open=101,
            high=106,
            low=99,
            close=102,
            volume=200,
        ),
    ]
    actions = [
        CorporateAction(
            action_id="split_2_1",
            instrument_id="NSE:TEST",
            symbol="TEST",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 1, 3),
            ratio_num=2,
            ratio_den=1,
            source="test",
            verified=True,
        )
    ]
    raw_snapshot = [(b.open, b.high, b.low, b.close, b.volume) for b in bars]
    adjusted = apply_adjustment_policy(bars, actions, default_split_bonus_policy())
    assert [(b.open, b.high, b.low, b.close, b.volume) for b in bars] == raw_snapshot
    assert adjusted[0].adjustment_factor == 2.0
    assert adjusted[0].adj_close == 100.0
    assert adjusted[1].adjustment_factor == 1.0
    assert adjusted[1].adj_close == 100.0
    assert adjusted[2].adjustment_factor == 1.0
    assert adjusted[2].adj_close == 102.0


def test_one_for_two_reverse_split():
    """1-for-2 reverse: r=0.5; pre-ex adj = raw / 0.5 = 2x raw."""
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=50,
            high=52,
            low=48,
            close=50,
            volume=100,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 3),
            symbol="TEST",
            open=100,
            high=105,
            low=95,
            close=100,
            volume=50,
        ),
    ]
    actions = [
        CorporateAction(
            action_id="rev_1_2",
            instrument_id="NSE:TEST",
            symbol="TEST",
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2024, 1, 3),
            ratio_num=1,
            ratio_den=2,
            source="test",
            verified=True,
        )
    ]
    adjusted = apply_adjustment_policy(bars, actions, default_split_bonus_policy())
    assert bars[0].close == 50
    assert adjusted[0].adjustment_factor == 0.5
    assert adjusted[0].adj_close == 100.0
    assert adjusted[1].adjustment_factor == 1.0
    assert adjusted[1].adj_close == 100.0


def test_bonus_issue_factor():
    """3-for-2 bonus ⇒ r=1.5; pre-ex prices divided by 1.5."""
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=150,
            high=150,
            low=150,
            close=150,
            volume=10,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 3),
            symbol="TEST",
            open=100,
            high=100,
            low=100,
            close=100,
            volume=15,
        ),
    ]
    actions = [
        CorporateAction(
            action_id="bonus_3_2",
            instrument_id="NSE:TEST",
            symbol="TEST",
            action_type=CorporateActionType.BONUS,
            ex_date=date(2024, 1, 3),
            ratio_num=3,
            ratio_den=2,
            source="test",
            verified=True,
        )
    ]
    adjusted = apply_adjustment_policy(bars, actions, default_split_bonus_policy())
    assert bars[0].close == 150
    assert adjusted[0].adjustment_factor == 1.5
    assert adjusted[0].adj_close == 100.0
    assert adjusted[1].adj_close == 100.0

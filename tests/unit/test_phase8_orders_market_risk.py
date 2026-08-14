"""Phase 8 — order state machine, market data, risk, kill switch."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantfund.paper.kill_switch import KillSwitch, KillSwitchState
from quantfund.paper.market_data import MarketDataValidator
from quantfund.paper.models import MarketDataEvent, deterministic_id
from quantfund.paper.orders import (
    BACKTEST_STATUS_MAP,
    InvalidPaperOrderTransition,
    PaperOrderStatus,
    make_order_intent,
    validate_order_structurally,
)
from quantfund.paper.risk import PaperRiskConfig, PaperRiskEngine
from quantfund.trading.models import Order, OrderSide, OrderStatus, OrderType
from tests.unit.test_phase8_helpers import (
    calendar_for_events,
    make_events,
    sample_instrument,
)


def _intent(qty: float = 10.0):
    order = Order(
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=qty,
        order_type=OrderType.MARKET,
    )
    return make_order_intent(session_id="s1", order=order, event_seq=0)


def test_paper_status_mapping_covers_all():
    for st in PaperOrderStatus:
        assert st in BACKTEST_STATUS_MAP


def test_deterministic_order_ids_stable():
    a = _intent()
    b = _intent()
    assert a.intent_id == b.intent_id
    assert a.order.order_id == b.order.order_id
    assert len(a.order.order_id) == 32


def test_order_lifecycle_happy_path():
    intent = _intent()
    assert intent.status == PaperOrderStatus.CREATED
    intent.transition(PaperOrderStatus.VALIDATED)
    intent.transition(PaperOrderStatus.ACCEPTED)
    assert intent.order.status == OrderStatus.SCHEDULED
    intent.transition(PaperOrderStatus.FILLED)
    assert intent.status == PaperOrderStatus.FILLED


def test_invalid_transition_fail_closed():
    intent = _intent()
    with pytest.raises(InvalidPaperOrderTransition):
        intent.transition(PaperOrderStatus.FILLED)


def test_created_to_rejected():
    intent = _intent()
    intent.transition(PaperOrderStatus.REJECTED, reason="bad")
    assert intent.reject_reason == "bad"
    assert intent.order.status == OrderStatus.REJECTED


def test_accepted_to_cancelled_and_expired():
    intent = _intent()
    intent.transition(PaperOrderStatus.VALIDATED)
    intent.transition(PaperOrderStatus.ACCEPTED)
    intent.transition(PaperOrderStatus.CANCELLED)
    intent2 = _intent()
    intent2.order.quantity = 11  # different id path — rebuild
    intent2 = make_order_intent(
        session_id="s1",
        order=Order(
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            symbol="AAA",
            side=OrderSide.BUY,
            quantity=11,
            order_type=OrderType.MARKET,
        ),
        event_seq=1,
    )
    intent2.transition(PaperOrderStatus.VALIDATED)
    intent2.transition(PaperOrderStatus.ACCEPTED)
    intent2.transition(PaperOrderStatus.EXPIRED)


def test_partial_then_filled():
    intent = _intent()
    intent.transition(PaperOrderStatus.VALIDATED)
    intent.transition(PaperOrderStatus.ACCEPTED)
    intent.transition(PaperOrderStatus.PARTIALLY_FILLED)
    intent.transition(PaperOrderStatus.FILLED)


def test_structural_invalid_quantity():
    order = Order(
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=1,
    )
    order.quantity = 0  # bypass constructor
    assert validate_order_structurally(order) == "invalid_quantity"


def test_market_duplicate_event_rejected():
    events = make_events(2)
    v = MarketDataValidator(calendar=calendar_for_events(events))
    assert v.validate(events[0]).ok
    assert v.validate(events[0]).ok is False
    assert v.validate(events[0]).reason == "duplicate_event"


def test_market_out_of_order_seq():
    events = make_events(2)
    v = MarketDataValidator(calendar=calendar_for_events(events))
    assert v.validate(events[1]).ok  # seq=1 first
    r = v.validate(events[0])  # seq=0 after
    assert r.ok is False
    assert r.reason == "out_of_order_event"


def test_market_stale_timestamp():
    events = make_events(2)
    v = MarketDataValidator(calendar=calendar_for_events(events), require_calendar_session=False)
    assert v.validate(events[1]).ok
    # craft older ts with higher seq — still stale by watermark
    bad = events[0].model_copy(
        update={
            "event_id": deterministic_id("bad"),
            "seq": 2,
            "timestamp": events[0].timestamp,
        }
    )
    # last watermark for symbol is events[1].timestamp > events[0]
    r = v.validate(bad)
    assert r.ok is False
    assert r.reason in {"stale_or_out_of_order", "duplicate_event"}


def test_invalid_ohlc_on_construct():
    with pytest.raises(Exception):
        MarketDataEvent(
            event_id="x",
            seq=0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            symbol="AAA",
            open=10,
            high=9,
            low=11,
            close=10,
        )


def test_unknown_instrument_rejected():
    events = make_events(1)
    v = MarketDataValidator(
        instruments=[sample_instrument("BBB")],
        require_known_instruments=True,
        require_calendar_session=False,
    )
    r = v.validate(events[0])
    assert r.ok is False
    assert r.reason == "unknown_instrument"


def test_market_closed_rejected():
    events = make_events(1)
    # calendar with no open sessions
    from quantfund.data.calendar.fake import FakeCalendarProvider

    cal = FakeCalendarProvider(open_sessions=[])
    v = MarketDataValidator(calendar=cal)
    r = v.validate(events[0])
    assert r.ok is False
    assert r.reason == "market_closed"


def test_kill_switch_activates_and_blocks_risk():
    ks = KillSwitch()
    assert ks.state == KillSwitchState.ARMED
    ks.activate(reason="drawdown", actor="op")
    assert ks.is_triggered
    engine = PaperRiskEngine(kill_switch=ks)
    intent = _intent()
    intent.transition(PaperOrderStatus.VALIDATED)
    d = engine.check_intent(
        intent,
        ref_price=100,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000,
    )
    assert d.accepted is False
    assert d.reason == "kill_switch"


def test_kill_switch_reset_requires_actor():
    ks = KillSwitch()
    ks.activate(reason="x", actor="a")
    with pytest.raises(ValueError):
        ks.reset(reason="ok", actor="")
    ks.reset(reason="manual", actor="op")
    assert ks.state == KillSwitchState.ARMED


def test_risk_max_order_notional():
    engine = PaperRiskEngine(PaperRiskConfig(max_order_notional=500))
    intent = _intent(qty=10)
    intent.transition(PaperOrderStatus.VALIDATED)
    d = engine.check_intent(
        intent,
        ref_price=100,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000,
    )
    assert d.accepted is False
    assert d.reason == "max_order_notional"


def test_risk_max_position_quantity():
    engine = PaperRiskEngine(PaperRiskConfig(max_position_quantity=5))
    intent = _intent(qty=10)
    intent.transition(PaperOrderStatus.VALIDATED)
    d = engine.check_intent(
        intent,
        ref_price=10,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000,
    )
    assert d.accepted is False
    assert d.reason == "max_position_quantity"


def test_risk_max_position_notional_via_core():
    engine = PaperRiskEngine(PaperRiskConfig(max_position_notional=100, max_order_notional=10_000))
    intent = _intent(qty=10)
    intent.transition(PaperOrderStatus.VALIDATED)
    d = engine.check_intent(
        intent,
        ref_price=50,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000,
    )
    assert d.accepted is False
    assert d.reason in {"max_position_notional", "max_gross_exposure"}


def test_risk_max_gross_exposure():
    engine = PaperRiskEngine(
        PaperRiskConfig(
            max_gross_exposure=100,
            max_order_notional=10_000,
            max_position_notional=10_000,
        )
    )
    intent = _intent(qty=10)
    intent.transition(PaperOrderStatus.VALIDATED)
    d = engine.check_intent(
        intent,
        ref_price=50,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000,
    )
    assert d.accepted is False
    assert d.reason == "max_gross_exposure"


def test_risk_max_order_count():
    engine = PaperRiskEngine(PaperRiskConfig(max_order_count=0))
    intent = _intent()
    intent.transition(PaperOrderStatus.VALIDATED)
    d = engine.check_intent(
        intent,
        ref_price=10,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000,
    )
    assert d.reason == "max_order_count"


def test_risk_max_turnover():
    engine = PaperRiskEngine(PaperRiskConfig(max_turnover=50))
    intent = _intent(qty=10)
    intent.transition(PaperOrderStatus.VALIDATED)
    d = engine.check_intent(
        intent,
        ref_price=10,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000,
    )
    assert d.reason == "max_turnover"


def test_risk_max_daily_loss():
    engine = PaperRiskEngine(PaperRiskConfig(max_daily_loss=10))
    engine.set_day_start_equity(100_000)
    intent = _intent(qty=1)
    intent.transition(PaperOrderStatus.VALIDATED)
    d = engine.check_intent(
        intent,
        ref_price=10,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000 - 50,
    )
    assert d.reason == "max_daily_loss"


def test_risk_accepts_within_limits():
    engine = PaperRiskEngine()
    intent = _intent(qty=1)
    intent.transition(PaperOrderStatus.VALIDATED)
    d = engine.check_intent(
        intent,
        ref_price=10,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000,
    )
    assert d.accepted is True

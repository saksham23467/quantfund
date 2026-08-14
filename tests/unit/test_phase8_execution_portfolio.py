"""Phase 8 — fills, execution, portfolio, reconciliation, audit."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantfund.paper.audit import PaperAuditLog
from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.paper.fills import PaperFillConfig, compute_fill_quantity, make_fill_id
from quantfund.paper.models import PartialFillPolicy
from quantfund.paper.orders import PaperOrderStatus, make_order_intent
from quantfund.paper.portfolio import PaperPortfolio
from quantfund.paper.reconciliation import reconcile_paper_state
from quantfund.trading.models import Order, OrderSide, OrderType


def _accepted_intent(qty: float = 10.0):
    order = Order(
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.BUY,
        quantity=qty,
        order_type=OrderType.MARKET,
    )
    intent = make_order_intent(session_id="s1", order=order, event_seq=0)
    intent.transition(PaperOrderStatus.VALIDATED)
    intent.transition(PaperOrderStatus.ACCEPTED)
    return intent


def test_deterministic_fill_ids():
    a = make_fill_id(
        session_id="s", order_id="o", fill_seq=1, symbol="AAA", quantity=1, price=10
    )
    b = make_fill_id(
        session_id="s", order_id="o", fill_seq=1, symbol="AAA", quantity=1, price=10
    )
    assert a == b


def test_partial_fill_quantity_policy():
    assert compute_fill_quantity(
        remaining_quantity=10,
        policy=PartialFillPolicy.ALL_OR_NOTHING,
        ratio=0.5,
    ) == 10
    assert compute_fill_quantity(
        remaining_quantity=10,
        policy=PartialFillPolicy.ALLOW_PARTIAL,
        ratio=0.5,
    ) == 5


def test_execution_applies_slippage_and_costs():
    adapter = PaperExecutionAdapter(session_id="s1", slippage_model_id="fixed_bps_5")
    intent = _accepted_intent(1)
    res = adapter.execute_at_open(
        intent,
        execution_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_price=100.0,
        cash=100_000,
        position_qty=0,
    )
    assert res.rejected is False
    assert res.fill is not None
    assert res.fill.price > 100.0  # buy adverse slippage
    assert res.fill.transaction_cost > 0
    assert intent.status == PaperOrderStatus.FILLED


def test_insufficient_cash_rejected():
    adapter = PaperExecutionAdapter(session_id="s1")
    intent = _accepted_intent(1000)
    res = adapter.execute_at_open(
        intent,
        execution_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_price=100.0,
        cash=10.0,
        position_qty=0,
    )
    assert res.rejected is True
    assert res.reason == "insufficient_cash"


def test_insufficient_position_rejected():
    adapter = PaperExecutionAdapter(session_id="s1")
    order = Order(
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.SELL,
        quantity=5,
        order_type=OrderType.MARKET,
    )
    intent = make_order_intent(session_id="s1", order=order, event_seq=2)
    intent.transition(PaperOrderStatus.VALIDATED)
    intent.transition(PaperOrderStatus.ACCEPTED)
    res = adapter.execute_at_open(
        intent,
        execution_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_price=100.0,
        cash=100_000,
        position_qty=1,
    )
    assert res.reason == "insufficient_position"


def test_market_closed_and_stale_reject():
    adapter = PaperExecutionAdapter(session_id="s1")
    intent = _accepted_intent(1)
    r1 = adapter.execute_at_open(
        intent,
        execution_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_price=100,
        cash=100_000,
        position_qty=0,
        market_closed=True,
    )
    assert r1.reason == "market_closed"
    intent2 = _accepted_intent(2)
    r2 = adapter.execute_at_open(
        intent2,
        execution_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_price=100,
        cash=100_000,
        position_qty=0,
        stale=True,
    )
    assert r2.reason == "stale_data"


def test_partial_fill_lifecycle():
    adapter = PaperExecutionAdapter(
        session_id="s1",
        fill_config=PaperFillConfig(
            partial_fill_policy=PartialFillPolicy.ALLOW_PARTIAL,
            partial_fill_ratio=0.5,
        ),
    )
    intent = _accepted_intent(10)
    res = adapter.execute_at_open(
        intent,
        execution_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_price=100,
        cash=100_000,
        position_qty=0,
    )
    assert res.fill is not None
    assert res.fill.quantity == 5
    assert intent.status == PaperOrderStatus.PARTIALLY_FILLED
    # Complete remainder at full remaining quantity
    adapter.fill_config = PaperFillConfig(
        partial_fill_policy=PartialFillPolicy.ALLOW_PARTIAL,
        partial_fill_ratio=1.0,
    )
    res2 = adapter.execute_at_open(
        intent,
        execution_time=datetime(2024, 1, 4, tzinfo=timezone.utc),
        open_price=100,
        cash=100_000,
        position_qty=5,
    )
    assert intent.status == PaperOrderStatus.FILLED
    assert res2.fill is not None
    assert res2.fill.quantity == 5


def test_position_and_cash_accounting():
    book = PaperPortfolio.create(100_000)
    adapter = PaperExecutionAdapter(session_id="s1")
    intent = _accepted_intent(10)
    res = adapter.execute_at_open(
        intent,
        execution_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_price=100,
        cash=book.cash_balance,
        position_qty=0,
    )
    book.apply_fill(res.fill)
    assert book.position_quantity("AAA") == 10
    assert book.cash_balance < 100_000
    assert len(book.positions.entries) == 1
    assert len(book.cash.entries) == 1


def test_realized_and_unrealized_pnl():
    book = PaperPortfolio.create(100_000)
    adapter = PaperExecutionAdapter(session_id="s1", slippage_model_id="fixed_bps_0")
    buy = _accepted_intent(10)
    br = adapter.execute_at_open(
        buy,
        execution_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_price=100,
        cash=book.cash_balance,
        position_qty=0,
    )
    book.apply_fill(br.fill)
    book.update_mark("AAA", 110)
    assert book.unrealized_pnl() > 0
    sell_order = Order(
        timestamp=datetime(2024, 1, 4, tzinfo=timezone.utc),
        symbol="AAA",
        side=OrderSide.SELL,
        quantity=10,
        order_type=OrderType.MARKET,
    )
    sell = make_order_intent(session_id="s1", order=sell_order, event_seq=3)
    sell.transition(PaperOrderStatus.VALIDATED)
    sell.transition(PaperOrderStatus.ACCEPTED)
    sr = adapter.execute_at_open(
        sell,
        execution_time=datetime(2024, 1, 5, tzinfo=timezone.utc),
        open_price=110,
        cash=book.cash_balance,
        position_qty=10,
    )
    book.apply_fill(sr.fill)
    assert book.realized_pnl() > 0
    assert book.position_quantity("AAA") == 0


def test_duplicate_fill_application_fails():
    book = PaperPortfolio.create(100_000)
    adapter = PaperExecutionAdapter(session_id="s1")
    intent = _accepted_intent(1)
    res = adapter.execute_at_open(
        intent,
        execution_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_price=100,
        cash=100_000,
        position_qty=0,
    )
    book.apply_fill(res.fill)
    with pytest.raises(ValueError, match="duplicate_fill"):
        book.apply_fill(res.fill)


def test_reconciliation_pass_and_fail():
    book = PaperPortfolio.create(100_000)
    adapter = PaperExecutionAdapter(session_id="s1")
    intent = _accepted_intent(1)
    res = adapter.execute_at_open(
        intent,
        execution_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_price=100,
        cash=100_000,
        position_qty=0,
    )
    book.apply_fill(res.fill)
    ok = reconcile_paper_state(book, fills=[res.fill], initial_cash=100_000)
    assert ok.ok is True
    book.portfolio.cash -= 50
    bad = reconcile_paper_state(book, fills=[res.fill], initial_cash=100_000)
    assert bad.ok is False
    assert any(i.code == "cash_mismatch" for i in bad.issues)


def test_audit_append_only_sequence(tmp_path):
    log = PaperAuditLog(session_id="s1")
    path = tmp_path / "audit.jsonl"
    log.bind_path(path)
    log.append("session_started", {"x": 1})
    log.append("market_event", {"y": 2})
    assert log.events[0].seq == 1
    assert log.events[1].prev_hash == log.events[0].event_hash
    log.freeze_check_immutable()
    # second bind fails (immutability of path)
    log2 = PaperAuditLog(session_id="s1")
    with pytest.raises(FileExistsError):
        log2.bind_path(path)


def test_strategy_cannot_import_execution_as_public_contract():
    import inspect

    import quantfund.strategies.base as base

    src = inspect.getsource(base)
    assert "paper.execution" not in src
    assert "PaperExecutionAdapter" not in src

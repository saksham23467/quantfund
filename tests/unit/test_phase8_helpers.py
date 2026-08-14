"""Shared helpers for Phase 8 tests (not counted as Phase 8 coverage alone)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.models import MarketDataEvent, PaperSessionConfig, SessionMode, deterministic_id
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.trading.models import Order, OrderSide, OrderType, Signal, SignalAction


class BuyOnceStrategy(Strategy):
    """Buy a fixed quantity once, then hold — deterministic paper fixture."""

    def __init__(self, symbol: str = "AAA", qty: float = 10.0) -> None:
        self.symbol = symbol
        self.qty = qty
        self._bought = False

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="buy_once",
            strategy_name="BuyOnce",
            strategy_version="1.0.0",
            parameters={"symbol": self.symbol, "qty": self.qty},
        )

    def generate_signal(self, context: StrategyContext) -> Signal:
        if self._bought or context.position_quantity > 0:
            return Signal(
                timestamp=context.timestamp,
                symbol=self.symbol,
                action=SignalAction.HOLD,
            )
        return Signal(
            timestamp=context.timestamp,
            symbol=self.symbol,
            action=SignalAction.BUY,
            target_quantity=self.qty,
        )

    def generate_orders(self, signal: Signal, context: StrategyContext) -> list[Order]:
        if signal.action != SignalAction.BUY or self._bought:
            return []
        self._bought = True
        return [
            Order(
                timestamp=context.timestamp,
                symbol=self.symbol,
                side=OrderSide.BUY,
                quantity=self.qty,
                order_type=OrderType.MARKET,
                signal_timestamp=signal.timestamp,
            )
        ]


class SellOnceStrategy(Strategy):
    def __init__(self, symbol: str = "AAA", qty: float = 5.0) -> None:
        self.symbol = symbol
        self.qty = qty
        self._sold = False

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="sell_once",
            strategy_name="SellOnce",
            strategy_version="1.0.0",
        )

    def generate_signal(self, context: StrategyContext) -> Signal:
        if self._sold or context.position_quantity <= 0:
            return Signal(
                timestamp=context.timestamp,
                symbol=self.symbol,
                action=SignalAction.HOLD,
            )
        return Signal(
            timestamp=context.timestamp,
            symbol=self.symbol,
            action=SignalAction.SELL,
            target_quantity=self.qty,
        )

    def generate_orders(self, signal: Signal, context: StrategyContext) -> list[Order]:
        if signal.action != SignalAction.SELL or self._sold:
            return []
        self._sold = True
        qty = min(self.qty, context.position_quantity)
        return [
            Order(
                timestamp=context.timestamp,
                symbol=self.symbol,
                side=OrderSide.SELL,
                quantity=qty,
                order_type=OrderType.MARKET,
                signal_timestamp=signal.timestamp,
            )
        ]


def make_events(
    n: int = 5,
    *,
    symbol: str = "AAA",
    start: date | None = None,
    base_price: float = 100.0,
) -> list[MarketDataEvent]:
    start = start or date(2024, 1, 2)
    events: list[MarketDataEvent] = []
    d = start
    i = 0
    while len(events) < n:
        if d.weekday() < 5:
            px = base_price + i
            ts = datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
            events.append(
                MarketDataEvent(
                    event_id=deterministic_id("ev", symbol, i, d.isoformat()),
                    seq=i,
                    timestamp=ts,
                    symbol=symbol,
                    open=px,
                    high=px + 1,
                    low=px - 1,
                    close=px + 0.5,
                    volume=1000 + i,
                    instrument_id=f"NSE:{symbol}",
                    session_date=d,
                    source="test",
                )
            )
            i += 1
        d += timedelta(days=1)
    return events


def sandbox_config(**overrides) -> PaperSessionConfig:
    data = dict(
        session_id="paper_test_session",
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        initial_cash=100_000.0,
        certified_eligibility="development_only",
        strategy_id="buy_once",
        strategy_version="1.0.0",
        seed="t",
    )
    data.update(overrides)
    return PaperSessionConfig(**data)


def calendar_for_events(events: list[MarketDataEvent]) -> FakeCalendarProvider:
    return FakeCalendarProvider(
        open_sessions=[e.resolved_session_date() for e in events],
        verified=True,
    )


def sample_instrument(symbol: str = "AAA") -> Instrument:
    return Instrument(
        symbol=symbol,
        exchange="NSE",
        isin="INE000A01000",
        instrument_id=f"NSE:{symbol}",
    )

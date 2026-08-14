#!/usr/bin/env python3
"""Phase 8 paper-trading kernel demo — infrastructure sandbox only.

Uses synthetic events. Does NOT claim paper eligibility or profitability.

Expected:
  Phase 8 Paper Kernel: PASS
  Replay deterministic: true
  Reconciliation: PASS
  Risk controls: PASS
  Kill switch: PASS
  Research eligibility: DEVELOPMENT_ONLY
  Paper eligible: false
  Infrastructure sandbox: true
  Broker: NONE
  Live trading: DISABLED
  Claims: NONE
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.eligibility import PaperEligibilityGate
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import (
    MarketDataEvent,
    PaperSessionConfig,
    SessionMode,
    deterministic_id,
)
from quantfund.paper.orders import PaperOrderStatus, make_order_intent
from quantfund.paper.replay import replay_deterministic, run_paper_session
from quantfund.paper.risk import PaperRiskConfig, PaperRiskEngine
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.trading.models import Order, OrderSide, OrderType, Signal, SignalAction


class DemoBuyStrategy(Strategy):
    def __init__(self, symbol: str = "RELIANCE", qty: float = 5.0) -> None:
        self.symbol = symbol
        self.qty = qty
        self._bought = False

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="phase8_demo_buy",
            strategy_name="Phase8DemoBuy",
            strategy_version="1.0.0",
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


def _events(symbol: str = "RELIANCE", n: int = 8) -> list[MarketDataEvent]:
    out: list[MarketDataEvent] = []
    d = date(2024, 1, 2)
    i = 0
    px = 100.0
    while len(out) < n:
        if d.weekday() < 5:
            ts = datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
            out.append(
                MarketDataEvent(
                    event_id=deterministic_id("p8demo", symbol, i),
                    seq=i,
                    timestamp=ts,
                    symbol=symbol,
                    open=px,
                    high=px + 1.5,
                    low=px - 1.0,
                    close=px + 0.25,
                    volume=10_000 + i,
                    instrument_id=f"NSE:{symbol}",
                    session_date=d,
                    source="phase8_demo_synthetic",
                )
            )
            px += 0.5
            i += 1
        d += timedelta(days=1)
    return out


def main() -> int:
    print("PHASE 8 — Paper trading kernel (infrastructure sandbox)")
    print("=" * 60)

    events = _events()
    calendar = FakeCalendarProvider(
        open_sessions=[e.resolved_session_date() for e in events],
        verified=True,
    )
    instruments = [
        Instrument(
            symbol="RELIANCE",
            exchange="NSE",
            isin="INE002A01018",
            instrument_id="NSE:RELIANCE",
        )
    ]
    cfg = PaperSessionConfig(
        session_id="phase8_demo_sandbox",
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        initial_cash=100_000.0,
        certified_eligibility="development_only",
        strategy_id="phase8_demo_buy",
        strategy_version="1.0.0",
        dataset_id="india_eq_pilot_phase35",
        dataset_version="v1_synthetic",
        seed="phase8_demo",
    )

    gate = PaperEligibilityGate().evaluate(
        certified_eligibility=cfg.certified_eligibility,
        session_mode=cfg.mode,
    )
    assert gate.paper_eligible is False

    # Kernel run
    result = run_paper_session(
        config=cfg,
        strategy=DemoBuyStrategy(),
        events=events,
        calendar=calendar,
        instruments=instruments,
    )
    kernel_pass = (
        not result.halted
        and result.reconciliation.ok
        and len(result.fills) >= 1
        and result.paper_eligible is False
    )

    # Deterministic replay
    rr = replay_deterministic(
        config=cfg,
        strategy_factory=lambda: DemoBuyStrategy(),
        events=events,
        calendar=calendar,
        instruments=instruments,
    )

    # Risk controls smoke
    risk_engine = PaperRiskEngine(PaperRiskConfig(max_order_notional=1.0))
    order = Order(
        timestamp=events[0].timestamp,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
    )
    intent = make_order_intent(session_id="risk_demo", order=order, event_seq=0)
    from quantfund.paper.orders import PaperOrderStatus

    intent.transition(PaperOrderStatus.VALIDATED)
    risk_decision = risk_engine.check_intent(
        intent,
        ref_price=100,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000,
    )
    risk_pass = risk_decision.accepted is False

    # Kill switch smoke
    ks = KillSwitch()
    ks.activate(reason="demo", actor="phase8_demo")
    ks_engine = PaperRiskEngine(kill_switch=ks)
    intent2 = make_order_intent(
        session_id="ks_demo",
        order=Order(
            timestamp=events[0].timestamp,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
        ),
        event_seq=1,
    )
    intent2.transition(PaperOrderStatus.VALIDATED)
    ks_decision = ks_engine.check_intent(
        intent2,
        ref_price=100,
        current_position_qty=0,
        current_exposure=0,
        current_equity=100_000,
    )
    kill_pass = ks_decision.reason == "kill_switch"

    print(f"Phase 8 Paper Kernel: {'PASS' if kernel_pass else 'FAIL'}")
    print(f"Orders: {len(result.orders)}")
    print(f"Fills: {len(result.fills)}")
    print(f"Replay deterministic: {str(rr.deterministic).lower()}")
    print(
        f"Reconciliation: {'PASS' if result.reconciliation.ok else 'FAIL'}"
    )
    print(f"Risk controls: {'PASS' if risk_pass else 'FAIL'}")
    print(f"Kill switch: {'PASS' if kill_pass else 'FAIL'}")
    print("Research eligibility: DEVELOPMENT_ONLY")
    print(f"Paper eligible: {str(result.paper_eligible).lower()}")
    print("Infrastructure sandbox: true")
    print("Broker: NONE")
    print("Live trading: DISABLED")
    print("Claims: NONE")
    print()
    print("Phase 8 complete — Phase 9 has NOT started.")
    return 0 if (
        kernel_pass and rr.deterministic and risk_pass and kill_pass
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())

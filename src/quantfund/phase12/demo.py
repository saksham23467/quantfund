"""Shared Phase 12 demo / harness helpers (offline fixture; no credentials)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.models import PaperSessionConfig, SessionMode
from quantfund.paper.replay import replay_deterministic
from quantfund.paper.risk import PaperRiskConfig
from quantfund.phase12.activation import (
    PAPER_ACTIVATION_CONFIRM_PHRASE,
    create_paper_activation_record,
)
from quantfund.phase12.engine import ControlledPaperEngine, ControlledPaperResult
from quantfund.phase12.market_data import MarketDataConfig, PaperMarketDataAdapter, make_fixture_events
from quantfund.phase12.reports import write_phase12_report
from quantfund.strategies.base import Strategy, StrategyContext, StrategyMetadata
from quantfund.trading.models import Order, OrderSide, OrderType, Signal, SignalAction


class Phase12DemoBuyStrategy(Strategy):
    """Deterministic buy-once strategy for Phase 12 demos/tests."""

    def __init__(self, symbol: str = "RELIANCE", qty: float = 5.0) -> None:
        self.symbol = symbol
        self.qty = qty
        self._bought = False

    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="phase12_demo_buy",
            strategy_name="Phase12DemoBuy",
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


def build_demo_context(
    *,
    session_id: str = "phase12_demo",
    out_dir: Path | None = None,
) -> dict[str, Any]:
    symbol = "RELIANCE"
    events = make_fixture_events(symbol=symbol, n=8)
    calendar = FakeCalendarProvider(
        open_sessions=[e.resolved_session_date() for e in events],
        verified=True,
    )
    instruments = [
        Instrument(
            symbol=symbol,
            exchange="NSE",
            isin="INE002A01018",
            instrument_id=f"NSE:{symbol}",
        )
    ]
    md_cfg = MarketDataConfig(symbols=(symbol,), provider="fixture")
    session_cfg = PaperSessionConfig(
        session_id=session_id,
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        initial_cash=100_000.0,
        certified_eligibility="development_only",
        strategy_id="phase12_demo_buy",
        strategy_version="1.0.0",
        dataset_id="phase12_fixture",
        dataset_version="v1",
        seed="phase12_demo",
        cost_model_id="equity_delivery_v1",
        slippage_model_id="fixed_bps_5",
        require_known_instruments=True,
    )
    risk = PaperRiskConfig(
        max_position_quantity=100.0,
        max_position_notional=50_000.0,
        max_order_notional=50_000.0,
        max_gross_exposure=100_000.0,
        max_order_count=20,
    )
    activation = create_paper_activation_record(
        operator_id="phase12_demo_operator",
        strategy_id=session_cfg.strategy_id,
        strategy_version=session_cfg.strategy_version,
        config_hash=session_cfg.config_hash(),
        risk_config_hash=f"risk:{risk.max_order_notional}:{risk.max_daily_loss}",
        market_data_config_hash=md_cfg.config_hash(),
        reason="phase12_controlled_simulation_demo",
        confirmation_phrase=PAPER_ACTIVATION_CONFIRM_PHRASE,
        timestamp="2024-01-02T00:00:00+00:00",
    )
    adapter = PaperMarketDataAdapter(
        md_cfg, instruments=instruments, calendar=calendar
    )
    batch = adapter.from_events(events)
    paths: dict[str, Path] = {}
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        paths["journal"] = out_dir / "paper_journal.jsonl"
        paths["snapshot"] = out_dir / "paper_state.json"
        paths["report_dir"] = out_dir
    return {
        "events": events,
        "calendar": calendar,
        "instruments": instruments,
        "md_cfg": md_cfg,
        "session_cfg": session_cfg,
        "risk": risk,
        "activation": activation,
        "batch": batch,
        "paths": paths,
    }


def run_phase12_demo(out_dir: Path | None = None) -> ControlledPaperResult:
    ctx = build_demo_context(out_dir=out_dir)
    engine = ControlledPaperEngine(
        session_config=ctx["session_cfg"],
        strategy_factory=lambda: Phase12DemoBuyStrategy(),
        activation=ctx["activation"],
        market_data_config=ctx["md_cfg"],
        risk_config=ctx["risk"],
        calendar=ctx["calendar"],
        instruments=ctx["instruments"],
        journal_path=ctx["paths"].get("journal"),
        snapshot_path=ctx["paths"].get("snapshot"),
        strategy_explicitly_enabled=True,
        strategy_spec_valid=True,
    )
    result = engine.run(
        ctx["events"],
        market_batch=ctx["batch"],
        backtest_order_count=1,
        backtest_signal_count=1,
        skip_replay_precheck=False,
    )
    if out_dir is not None:
        write_phase12_report(result, out_dir)
    return result


def run_phase12_replay_pair() -> dict[str, Any]:
    ctx = build_demo_context(session_id="phase12_replay")
    rr = replay_deterministic(
        config=ctx["session_cfg"],
        strategy_factory=lambda: Phase12DemoBuyStrategy(),
        events=ctx["events"],
        calendar=ctx["calendar"],
        instruments=ctx["instruments"],
        risk_config=ctx["risk"],
    )
    return {
        "identical": rr.deterministic,
        "hash_a": rr.first.state_hash,
        "hash_b": rr.second.state_hash,
        "paper_orders": len(rr.first.orders),
        "paper_fills": len(rr.first.fills),
        "live_orders": 0,
    }

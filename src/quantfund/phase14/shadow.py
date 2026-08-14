"""SHADOW mode — observe signals/orders/risk without portfolio or broker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.models import PaperSessionConfig
from quantfund.paper.risk import PaperRiskConfig, PaperRiskEngine
from quantfund.paper.orders import make_order_intent, validate_order_structurally
from quantfund.phase14.market_data import RealTimeBar, RealTimeMarketDataProvider
from quantfund.phase14.realtime import BarProcessResult, RealTimeEngineBase, RuntimeMode
from quantfund.strategies.base import Strategy, StrategyContext
from quantfund.trading.models import SignalAction


@dataclass
class ShadowResult:
    would_orders: list[dict[str, Any]] = field(default_factory=list)
    would_fills: list[dict[str, Any]] = field(default_factory=list)
    would_rejects: list[dict[str, Any]] = field(default_factory=list)
    signals: int = 0
    bars_received: int = 0
    live_orders: int = 0
    broker_submissions: int = 0
    mode: str = RuntimeMode.SHADOW.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "would_orders": len(self.would_orders),
            "would_fills": len(self.would_fills),
            "would_rejects": len(self.would_rejects),
            "signals": self.signals,
            "bars_received": self.bars_received,
            "live_orders": 0,
            "broker_submissions": 0,
            "claims": "NONE",
        }


class ShadowEngine(RealTimeEngineBase):
    """Generate WOULD_* events only — no fills, no broker."""

    def __init__(
        self,
        *,
        provider: RealTimeMarketDataProvider,
        strategy_factory: Callable[[], Strategy],
        session_config: PaperSessionConfig,
        calendar: CalendarProvider,
        instruments: list[Instrument] | None = None,
        risk_config: PaperRiskConfig | None = None,
        journal_path=None,
        max_staleness_seconds: float | None = 3600.0,
        daily_bar_mode: bool = True,
    ) -> None:
        super().__init__(
            mode=RuntimeMode.SHADOW,
            provider=provider,
            strategy_factory=strategy_factory,
            session_config=session_config,
            calendar=calendar,
            instruments=instruments,
            journal_path=journal_path,
            max_staleness_seconds=max_staleness_seconds,
            daily_bar_mode=daily_bar_mode,
        )
        self.risk = PaperRiskEngine(risk_config, kill_switch=self.kill_switch)
        self.result = ShadowResult()
        self._pending_would: list[dict[str, Any]] = []

    def process(self, bar: RealTimeBar) -> BarProcessResult:
        base = self.ingest_bar(bar)
        self.result.bars_received = self.bars_received
        self.result.signals = self.signals

        # Estimate fills for prior would-orders at this open (observation only)
        still = []
        for wo in self._pending_would:
            if wo.get("exec_seq") == bar.sequence and wo.get("symbol") == bar.symbol:
                self.result.would_fills.append(
                    {
                        "type": "WOULD_FILL",
                        "symbol": bar.symbol,
                        "price": bar.open,
                        "quantity": wo.get("quantity"),
                        "timestamp": bar.timestamp.isoformat(),
                    }
                )
                self.journal.append(
                    "FILL",
                    {"would": True, "price": bar.open, "quantity": wo.get("quantity")},
                    timestamp=bar.timestamp,
                    symbol=bar.symbol,
                )
            else:
                still.append(wo)
        self._pending_would = still

        if base.signal is None or not base.allows_new_orders:
            return base

        ctx = StrategyContext(
            timestamp=bar.timestamp,
            symbol=bar.symbol,
            history=list(self.history),
            position_quantity=0.0,
            cash=self.session_config.initial_cash,
            features=base.features,
            membership="TRUE",
        )
        orders = self.strategy.generate_orders(base.signal, ctx)
        for order in orders:
            intent = make_order_intent(
                session_id=self.session_config.session_id,
                order=order,
                signal=base.signal,
                event_seq=bar.sequence,
            )
            self.journal.append("ORDER_CREATED", {"would": True, **intent.to_mapping_dict()})
            self.journal.append(
                "RISK_CHECK",
                {"phase": "shadow"},
                timestamp=bar.timestamp,
                symbol=bar.symbol,
            )
            struct = validate_order_structurally(order)
            if struct:
                rec = {
                    "type": "WOULD_REJECT",
                    "reason": struct,
                    "timestamp": bar.timestamp.isoformat(),
                    "strategy": self.strategy.metadata().strategy_id,
                    "symbol": order.symbol,
                    "requested_quantity": order.quantity,
                }
                self.result.would_rejects.append(rec)
                self.journal.append("ORDER_REJECTED", rec)
                continue
            decision = self.risk.check_intent(
                intent,
                ref_price=bar.close,
                current_position_qty=0.0,
                current_exposure=0.0,
                current_equity=self.session_config.initial_cash,
            )
            if not decision.accepted:
                rec = {
                    "type": "WOULD_REJECT",
                    "risk_decision": "REJECT",
                    "reason": decision.reason,
                    "timestamp": bar.timestamp.isoformat(),
                    "strategy": self.strategy.metadata().strategy_id,
                    "symbol": order.symbol,
                    "requested_quantity": order.quantity,
                }
                self.result.would_rejects.append(rec)
                self.journal.append("ORDER_REJECTED", rec)
                continue
            would = {
                "type": "WOULD_ORDER",
                "symbol": order.symbol,
                "quantity": order.quantity,
                "side": order.side.value,
                "exec_seq": bar.sequence + 1,
                "signal_action": base.signal.action.value,
            }
            self.result.would_orders.append(would)
            self._pending_would.append(would)
            self.journal.append("ORDER_ACCEPTED", {"would": True, **would})
        return base

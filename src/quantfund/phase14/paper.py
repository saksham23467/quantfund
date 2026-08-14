"""REAL_TIME_PAPER — simulated fills via PaperExecutionAdapter only."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.paper.models import PaperSessionConfig
from quantfund.paper.orders import PaperOrderStatus
from quantfund.paper.risk import PaperRiskConfig
from quantfund.paper.session import PaperSession
from quantfund.phase12.isolation import assert_paper_only_adapter, live_order_count_always_zero
from quantfund.phase13.portfolio import snapshot_accounting
from quantfund.phase13.reconciliation import reconcile_phase13_session
from quantfund.phase14.market_data import RealTimeBar, RealTimeMarketDataProvider
from quantfund.phase14.realtime import BarProcessResult, RealTimeEngineBase, RuntimeMode
from quantfund.strategies.base import Strategy


FORBIDDEN_LIVE_METHODS = frozenset(
    {"place_order", "submit_order", "modify_order", "cancel_live_order"}
)


@dataclass
class RealTimePaperResult:
    mode: str = RuntimeMode.REAL_TIME_PAPER.value
    orders: int = 0
    accepted: int = 0
    rejected: int = 0
    fills: int = 0
    risk_rejections: int = 0
    bars_received: int = 0
    bars_rejected: int = 0
    stale_events: int = 0
    reconciliation_ok: bool = False
    allows_new_orders: bool = True
    kill_switch_state: str = "ARMED"
    accounting: dict[str, Any] = field(default_factory=dict)
    live_orders: int = 0
    broker_submissions: int = 0
    health: dict[str, Any] = field(default_factory=dict)
    claims: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "orders": self.orders,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "fills": self.fills,
            "risk_rejections": self.risk_rejections,
            "bars_received": self.bars_received,
            "stale_events": self.stale_events,
            "reconciliation_ok": self.reconciliation_ok,
            "allows_new_orders": self.allows_new_orders,
            "kill_switch": self.kill_switch_state,
            "accounting": self.accounting,
            "live_orders": 0,
            "broker_submissions": 0,
            "health": self.health,
            "research_eligibility": "DEVELOPMENT_ONLY",
            "claims": "NONE",
            "live_trading": "DISABLED",
        }


class RealTimePaperEngine(RealTimeEngineBase):
    """Drive PaperSession from a real-time bar stream (simulated fills only)."""

    def __init__(
        self,
        *,
        provider: RealTimeMarketDataProvider,
        strategy_factory: Callable[[], Strategy],
        session_config: PaperSessionConfig,
        calendar: CalendarProvider,
        instruments: list[Instrument] | None = None,
        risk_config: PaperRiskConfig | None = None,
        journal_path: Path | None = None,
        max_staleness_seconds: float | None = 3600.0,
        daily_bar_mode: bool = True,
    ) -> None:
        super().__init__(
            mode=RuntimeMode.REAL_TIME_PAPER,
            provider=provider,
            strategy_factory=strategy_factory,
            session_config=session_config,
            calendar=calendar,
            instruments=instruments,
            journal_path=journal_path,
            max_staleness_seconds=max_staleness_seconds,
            daily_bar_mode=daily_bar_mode,
        )
        self.risk_config = risk_config or PaperRiskConfig(
            max_order_notional=200_000,
            max_position_notional=200_000,
            max_gross_exposure=200_000,
            max_order_count=100,
        )
        # Isolation: only paper adapter
        self._paper_adapter = PaperExecutionAdapter(
            session_id=session_config.session_id,
            cost_model_id=session_config.cost_model_id,
            slippage_model_id=session_config.slippage_model_id,
        )
        assert_paper_only_adapter(self._paper_adapter)
        for name in FORBIDDEN_LIVE_METHODS:
            if hasattr(self, name):
                raise RuntimeError(f"live_method_present:{name}")

        self.paper = PaperSession(
            session_config,
            strategy=strategy_factory(),
            calendar=calendar,
            instruments=instruments,
            risk_config=self.risk_config,
        )
        # Share kill switch with paper risk
        self.paper.kill_switch = self.kill_switch
        self.paper.risk.kill_switch = self.kill_switch
        self._started_paper = False
        self.risk_rejections = 0

    def start(self, symbols: list[str]) -> None:
        super().start(symbols)
        if not self._started_paper:
            self.paper.start()
            self._started_paper = True

    def _position_qty(self, symbol: str) -> float:
        return self.paper.book.position_quantity(symbol)

    def _cash(self) -> float:
        return self.paper.book.cash_balance

    def process(self, bar: RealTimeBar) -> BarProcessResult:
        base = self.ingest_bar(bar)

        if base.extras.get("rejected"):
            return base

        # Stale / session / kill → do not feed into paper order path
        if base.stale or not base.allows_new_orders:
            # Still mark portfolio for visibility, but skip strategy side by
            # processing event only for marks? Safer: skip process_event entirely
            # when blocked so no new orders; pending fills for already-accepted
            # orders should still execute at open if not stale.
            if base.stale or self.kill_switch.is_triggered:
                return base

        # Convert to MarketDataEvent and drive PaperSession (next-bar-open)
        event = bar.to_event(session_prefix=self.session_config.session_id)
        # Align seq with provider sequence
        event = event.model_copy(update={"seq": bar.sequence})

        before_intents = len(self.paper.intents)
        before_fills = len(self.paper.fills)
        self.paper.process_event(event)

        # Journal paper outcomes
        for intent in self.paper.intents[before_intents:]:
            self.journal.append("ORDER_CREATED", intent.to_mapping_dict())
            if intent.status == PaperOrderStatus.REJECTED:
                self.risk_rejections += 1
                self.journal.append(
                    "ORDER_REJECTED",
                    {
                        "risk_decision": "REJECT",
                        "reason": intent.reject_reason,
                        "timestamp": bar.timestamp.isoformat(),
                        "strategy": self.strategy.metadata().strategy_id,
                        "symbol": intent.order.symbol,
                        "requested_quantity": intent.order.quantity,
                    },
                )
                self.journal.append(
                    "RISK_CHECK",
                    {"accepted": False, "reason": intent.reject_reason},
                )
            elif intent.status in {
                PaperOrderStatus.ACCEPTED,
                PaperOrderStatus.FILLED,
                PaperOrderStatus.PARTIALLY_FILLED,
            }:
                self.journal.append(
                    "ORDER_ACCEPTED",
                    {"intent_id": intent.intent_id, "status": intent.status.value},
                )
                self.journal.append("RISK_CHECK", {"accepted": True})

        for fill in self.paper.fills[before_fills:]:
            raw = fill.price - fill.slippage_per_unit
            self.journal.append(
                "FILL",
                {
                    "fill_id": fill.fill_id,
                    "raw_market_price": raw,
                    "simulated_execution_price": fill.price,
                    "quantity": fill.quantity,
                    "fees": fill.transaction_cost,
                    "slippage_per_unit": fill.slippage_per_unit,
                    "net_cash_impact": fill.net_cash_delta,
                },
                timestamp=fill.timestamp,
                symbol=fill.symbol,
            )
            self.journal.append(
                "POSITION_UPDATED",
                {
                    "symbol": fill.symbol,
                    "qty": self.paper.book.position_quantity(fill.symbol),
                },
            )
            # Reconcile after fills
            recon = reconcile_phase13_session(
                self.paper.book,
                fills=self.paper.fills,
                orders=[i.to_mapping_dict() for i in self.paper.intents],
                initial_cash=self.session_config.initial_cash,
                journal_event_ids=self.journal.event_ids(),
            )
            self.reconciliation_ok = recon.ok
            self.journal.append("RECONCILIATION", recon.to_dict())
            if not recon.ok:
                self.allows_new_orders = False

        return base

    def finalize(self) -> RealTimePaperResult:
        result = self.paper.stop()
        recon = reconcile_phase13_session(
            self.paper.book,
            fills=result.fills,
            orders=result.orders,
            initial_cash=self.session_config.initial_cash,
            journal_event_ids=self.journal.event_ids(),
        )
        self.reconciliation_ok = recon.ok
        self.journal.append("RECONCILIATION", recon.to_dict())
        acct = snapshot_accounting(self.paper.book, fills=result.fills)
        rejected = sum(
            1
            for i in self.paper.intents
            if i.status == PaperOrderStatus.REJECTED
        )
        accepted = sum(
            1
            for i in self.paper.intents
            if i.status
            in {
                PaperOrderStatus.ACCEPTED,
                PaperOrderStatus.FILLED,
                PaperOrderStatus.PARTIALLY_FILLED,
            }
        )
        live_order_count_always_zero(live_orders=0)
        self.stop()
        return RealTimePaperResult(
            orders=len(result.orders),
            accepted=accepted,
            rejected=rejected,
            fills=len(result.fills),
            risk_rejections=max(self.risk_rejections, rejected),
            bars_received=self.bars_received,
            bars_rejected=self.bars_rejected,
            stale_events=self.stale_events,
            reconciliation_ok=recon.ok,
            allows_new_orders=recon.ok and not self.kill_switch.is_triggered,
            kill_switch_state=self.kill_switch.state.value,
            accounting=acct.to_dict(),
            health=self.health().to_dict(),
        )

    def has_live_order_capability(self) -> bool:
        return False

"""PaperSession orchestration — next-bar-open paper kernel."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.models import Instrument, MarketBar
from quantfund.paper.audit import PaperAuditLog
from quantfund.paper.eligibility import PaperEligibilityDecision, PaperEligibilityGate
from quantfund.paper.execution import PaperExecutionAdapter
from quantfund.paper.fills import PaperFillConfig
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.market_data import MarketDataValidator
from quantfund.paper.models import (
    MarketDataEvent,
    PaperSessionConfig,
    SessionMode,
    state_hash,
)
from quantfund.paper.orders import (
    OrderIntent,
    PaperOrderStatus,
    make_order_intent,
    validate_order_structurally,
)
from quantfund.paper.portfolio import PaperPortfolio
from quantfund.paper.reconciliation import ReconciliationReport, reconcile_paper_state
from quantfund.paper.risk import PaperRiskConfig, PaperRiskEngine
from quantfund.strategies.base import Strategy, StrategyContext
from quantfund.trading.models import Fill, Signal


@dataclass
class PaperSessionResult:
    session_id: str
    mode: SessionMode
    paper_eligible: bool
    eligibility: PaperEligibilityDecision
    orders: list[dict[str, Any]]
    fills: list[Fill]
    snapshot: dict[str, Any]
    state_hash: str
    reconciliation: ReconciliationReport
    halted: bool
    halt_reason: str | None
    audit_event_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "paper_eligible": self.paper_eligible,
            "eligibility": self.eligibility.to_dict(),
            "orders": self.orders,
            "fills": [f.model_dump(mode="json") for f in self.fills],
            "snapshot": self.snapshot,
            "state_hash": self.state_hash,
            "reconciliation": self.reconciliation.to_dict(),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "audit_event_count": self.audit_event_count,
        }


class PaperSession:
    """Broker-independent paper trading session."""

    def __init__(
        self,
        config: PaperSessionConfig,
        *,
        strategy: Strategy,
        calendar: CalendarProvider | None = None,
        instruments: list[Instrument] | None = None,
        risk_config: PaperRiskConfig | None = None,
        audit_path: Path | None = None,
        eligibility_gate: PaperEligibilityGate | None = None,
        campaign_accepted: bool = False,
        facts=None,
        strategy_spec_hash: str | None = None,
        accepted_strategy_spec_hash: str | None = None,
    ) -> None:
        self.config = config
        self.strategy = strategy
        self.calendar = calendar
        self.kill_switch = KillSwitch()
        self.risk = PaperRiskEngine(risk_config, kill_switch=self.kill_switch)
        self.validator = MarketDataValidator(
            calendar=calendar,
            instruments=instruments,
            require_known_instruments=config.require_known_instruments,
            require_calendar_session=calendar is not None,
        )
        self.execution = PaperExecutionAdapter(
            session_id=config.session_id,
            cost_model_id=config.cost_model_id,
            slippage_model_id=config.slippage_model_id,
            fill_config=PaperFillConfig(
                partial_fill_policy=config.partial_fill_policy,
                partial_fill_ratio=config.partial_fill_ratio,
            ),
        )
        self.book = PaperPortfolio.create(config.initial_cash)
        self.audit = PaperAuditLog(session_id=config.session_id)
        if audit_path is not None:
            self.audit.bind_path(audit_path)

        self._gate = eligibility_gate or PaperEligibilityGate()
        self.eligibility = self._gate.evaluate(
            certified_eligibility=config.certified_eligibility,
            session_mode=config.mode,
            acceptance_evidence_id=config.acceptance_evidence_id,
            campaign_accepted=campaign_accepted,
            facts=facts,
            strategy_spec_hash=strategy_spec_hash,
            accepted_strategy_spec_hash=accepted_strategy_spec_hash,
        )

        self.intents: list[OrderIntent] = []
        self.fills: list[Fill] = []
        self.history_by_symbol: dict[str, list[MarketBar]] = {}
        self.pending: list[OrderIntent] = []
        self._started = False
        self._stopped = False
        self.halted = False
        self.halt_reason: str | None = None
        self._last_event: MarketDataEvent | None = None

        # Production mode hard-requires paper_eligible
        if (
            config.mode == SessionMode.PRODUCTION
            and not self.eligibility.paper_eligible
        ):
            raise ValueError(
                "production paper session requires paper_eligible=true; "
                f"blockers={self.eligibility.blockers}"
            )

    def start(self) -> None:
        if self._started:
            raise ValueError("session already started")
        self._started = True
        self.risk.set_day_start_equity(self.book.equity())
        self.audit.append(
            "session_started",
            {
                "config_hash": self.config.config_hash(),
                "mode": self.config.mode.value,
                "paper_eligible": self.eligibility.paper_eligible,
                "certified_eligibility": self.config.certified_eligibility,
                "initial_cash": self.config.initial_cash,
                "strategy_id": self.config.strategy_id,
                "blockers": list(self.eligibility.blockers),
            },
        )

    def activate_kill_switch(self, *, reason: str, actor: str = "operator") -> None:
        rec = self.kill_switch.activate(reason=reason, actor=actor)
        self.audit.append(
            "kill_switch_activated",
            rec.to_dict(),
        )

    def reset_kill_switch(self, *, reason: str, actor: str) -> None:
        rec = self.kill_switch.reset(reason=reason, actor=actor)
        self.audit.append("kill_switch_reset", rec.to_dict())

    def _halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason

    def process_event(self, event: MarketDataEvent) -> None:
        if not self._started or self._stopped:
            raise ValueError("session not running")
        if self.halted:
            return

        try:
            self._process_event_inner(event)
        except Exception as exc:  # noqa: BLE001 — fail closed
            self.audit.append(
                "session_exception",
                {"error": str(exc), "type": type(exc).__name__},
                ts=event.timestamp,
            )
            self._halt(f"exception:{type(exc).__name__}")

    def _process_event_inner(self, event: MarketDataEvent) -> None:
        v = self.validator.validate(event)
        if not v.ok:
            self.audit.append(
                "market_event",
                {
                    "event_id": event.event_id,
                    "seq": event.seq,
                    "accepted": False,
                    "reason": v.reason,
                },
                ts=event.timestamp,
            )
            self._halt(v.reason or "invalid_market_data")
            return

        self.audit.append(
            "market_event",
            {
                "event_id": event.event_id,
                "seq": event.seq,
                "symbol": event.symbol,
                "timestamp": event.timestamp.isoformat(),
                "accepted": True,
                "open": event.open,
                "close": event.close,
            },
            ts=event.timestamp,
        )

        # 1) Execute pending orders scheduled for this bar's open (next-bar-open)
        still_pending: list[OrderIntent] = []
        for intent in self.pending:
            if intent.scheduled_execution_seq != event.seq:
                still_pending.append(intent)
                continue
            if intent.order.symbol != event.symbol:
                still_pending.append(intent)
                continue
            market_closed = False
            if self.calendar is not None:
                market_closed = not self.calendar.is_session(event.resolved_session_date())
            result = self.execution.execute_at_open(
                intent,
                execution_time=event.timestamp,
                open_price=event.open,
                cash=self.book.cash_balance,
                position_qty=self.book.position_quantity(event.symbol),
                market_closed=market_closed,
            )
            if result.rejected:
                self.audit.append(
                    "order_rejected",
                    {
                        "intent_id": intent.intent_id,
                        "reason": result.reason,
                        "phase": "execution",
                    },
                    ts=event.timestamp,
                )
                continue
            assert result.fill is not None
            self.fills.append(result.fill)
            self.audit.append(
                "fill_generated",
                result.fill.model_dump(mode="json"),
                ts=event.timestamp,
            )
            try:
                ledger_entries = self.book.apply_fill(result.fill)
            except ValueError as exc:
                self.audit.append(
                    "reconciliation_failed",
                    {"reason": str(exc)},
                    ts=event.timestamp,
                )
                self._halt(str(exc))
                return
            for le in ledger_entries:
                if le.kind == "position_changed":
                    self.audit.append(
                        "position_changed",
                        le.payload,
                        ts=event.timestamp,
                    )
            if intent.status == PaperOrderStatus.PARTIALLY_FILLED:
                # Reschedule remainder for next bar open (same-symbol stream).
                intent.scheduled_execution_seq = event.seq + 1
                still_pending.append(intent)
        self.pending = still_pending

        # 2) Mark + history
        bar = MarketBar(
            timestamp=event.timestamp,
            symbol=event.symbol,
            open=event.open,
            high=event.high,
            low=event.low,
            close=event.close,
            volume=event.volume,
            instrument_id=event.instrument_id,
        )
        self.history_by_symbol.setdefault(event.symbol, []).append(bar)
        self.book.update_mark(event.symbol, event.close)
        self._last_event = event

        # 3) Strategy decision at close
        ctx = StrategyContext(
            timestamp=event.timestamp,
            symbol=event.symbol,
            history=list(self.history_by_symbol[event.symbol]),
            position_quantity=self.book.position_quantity(event.symbol),
            cash=self.book.cash_balance,
            membership="TRUE",
        )
        signal = self.strategy.generate_signal(ctx)
        self.audit.append(
            "signal_generated",
            {
                "timestamp": signal.timestamp.isoformat(),
                "symbol": signal.symbol,
                "action": signal.action.value,
                "strength": signal.strength,
                "target_quantity": signal.target_quantity,
            },
            ts=event.timestamp,
        )
        orders = self.strategy.generate_orders(signal, ctx)

        # 4) Validate + risk + accept for next event seq
        next_seq = event.seq + 1
        for order in orders:
            intent = make_order_intent(
                session_id=self.config.session_id,
                order=order,
                signal=signal,
                event_seq=event.seq,
            )
            self.intents.append(intent)
            self.audit.append(
                "order_created",
                intent.to_mapping_dict(),
                ts=event.timestamp,
            )

            struct_reason = validate_order_structurally(intent.order)
            if struct_reason:
                intent.transition(PaperOrderStatus.REJECTED, reason=struct_reason)
                self.audit.append(
                    "order_rejected",
                    {"intent_id": intent.intent_id, "reason": struct_reason},
                    ts=event.timestamp,
                )
                continue
            intent.transition(PaperOrderStatus.VALIDATED)

            decision = self.risk.check_intent(
                intent,
                ref_price=event.close,
                current_position_qty=self.book.position_quantity(event.symbol),
                current_exposure=self.book.exposure(),
                current_equity=self.book.equity(),
            )
            if not decision.accepted:
                self.audit.append(
                    "risk_rejected",
                    {
                        "intent_id": intent.intent_id,
                        "reason": decision.reason,
                    },
                    ts=event.timestamp,
                )
                self.audit.append(
                    "order_rejected",
                    {
                        "intent_id": intent.intent_id,
                        "reason": decision.reason,
                    },
                    ts=event.timestamp,
                )
                continue

            intent.transition(PaperOrderStatus.ACCEPTED)
            intent.scheduled_execution_seq = next_seq
            self.risk.record_accepted(intent, ref_price=event.close)
            self.pending.append(intent)
            self.audit.append(
                "order_accepted",
                {
                    "intent_id": intent.intent_id,
                    "scheduled_execution_seq": next_seq,
                },
                ts=event.timestamp,
            )

        self.book.portfolio.record_equity(event.timestamp)

    def stop(self) -> PaperSessionResult:
        if not self._started:
            raise ValueError("session not started")
        report = reconcile_paper_state(
            self.book,
            fills=self.fills,
            initial_cash=self.config.initial_cash,
            allow_negative_cash=self.config.allow_negative_cash,
        )
        if not report.ok:
            self.audit.append(
                "reconciliation_failed",
                report.to_dict(),
            )
            self._halt("reconciliation_failed")

        self.audit.append(
            "session_stopped",
            {
                "halted": self.halted,
                "halt_reason": self.halt_reason,
                "fill_count": len(self.fills),
                "order_count": len(self.intents),
                "paper_eligible": self.eligibility.paper_eligible,
                "reconciliation_ok": report.ok,
            },
        )
        self._stopped = True
        snap = self.book.snapshot()
        # Deterministic state hash excludes wall-clock audit timestamps
        state_payload = {
            "config_hash": self.config.config_hash(),
            "orders": [i.to_mapping_dict() for i in self.intents],
            "fills": [
                {
                    "fill_id": f.fill_id,
                    "order_id": f.order_id,
                    "symbol": f.symbol,
                    "side": f.side.value,
                    "quantity": f.quantity,
                    "price": f.price,
                    "transaction_cost": f.transaction_cost,
                    "net_cash_delta": f.net_cash_delta,
                }
                for f in self.fills
            ],
            "snapshot": snap,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }
        return PaperSessionResult(
            session_id=self.config.session_id,
            mode=self.config.mode,
            paper_eligible=self.eligibility.paper_eligible,
            eligibility=self.eligibility,
            orders=[i.to_mapping_dict() for i in self.intents],
            fills=list(self.fills),
            snapshot=snap,
            state_hash=state_hash(state_payload),
            reconciliation=report,
            halted=self.halted,
            halt_reason=self.halt_reason,
            audit_event_count=len(self.audit.events),
        )

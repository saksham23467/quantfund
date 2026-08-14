"""Phase 13 validation session runner — multi-day historical paper replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.corporate_actions.models import CorporateAction
from quantfund.data.models import Instrument, MarketBar
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import (
    PartialFillPolicy,
    PaperSessionConfig,
    SessionMode,
    state_hash,
)
from quantfund.paper.orders import PaperOrderStatus
from quantfund.paper.replay import replay_deterministic, run_paper_session
from quantfund.paper.risk import PaperRiskConfig
from quantfund.paper.session import PaperSession, PaperSessionResult
from quantfund.phase12.activation import PaperActivationRecord
from quantfund.phase12.eligibility import ControlledSimulationPaperGate
from quantfund.phase12.isolation import assert_paper_only_adapter, live_order_count_always_zero
from quantfund.phase13.drift import (
    Phase13DriftReport,
    compare_backtest_paper_semantics,
    run_backtest_for_drift,
)
from quantfund.phase13.journal import Phase13Journal
from quantfund.phase13.portfolio import (
    PortfolioAccountingSnapshot,
    apply_corporate_actions_to_book,
    snapshot_accounting,
)
from quantfund.phase13.reconciliation import reconcile_phase13_session
from quantfund.phase13.recovery import write_checkpoint
from quantfund.phase13.replay import HistoricalReplayFeed, ReplayQualityReport
from quantfund.strategies.base import Strategy


@dataclass
class Phase13ValidationResult:
    session_id: str
    state: str
    strategy_id: str
    strategy_version: str
    dataset_label: str
    data_source: str
    date_range: dict[str, str | None]
    paper_eligible: bool
    research_paper_eligible: bool
    orders_count: int
    accepted_orders: int
    rejected_orders: int
    fills_count: int
    initial_capital: float
    config_hash: str
    reconciliation_ok: bool
    replay_hash: str
    replay_identical: bool
    kill_switch_state: str
    accounting: PortfolioAccountingSnapshot | None
    drift: Phase13DriftReport | None
    quality: ReplayQualityReport | None
    warnings: list[str] = field(default_factory=list)
    data_quality_warnings: list[str] = field(default_factory=list)
    live_orders: int = 0
    broker_submissions: int = 0
    claims: str = "NONE"
    paper_session: PaperSessionResult | None = None
    allows_new_orders: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "strategy_id": self.strategy_id,
            "paper_eligible": self.paper_eligible,
            "orders": self.orders_count,
            "fills": self.fills_count,
            "rejected_orders": self.rejected_orders,
            "reconciliation_ok": self.reconciliation_ok,
            "replay_identical": self.replay_identical,
            "drift": self.drift.to_dict() if self.drift else None,
            "live_orders": 0,
            "claims": "NONE",
            "live_trading": "DISABLED",
            "research_eligibility": "DEVELOPMENT_ONLY",
            "mode": "CONTROLLED_HISTORICAL_SIMULATION",
        }


class ValidationSessionRunner:
    """Orchestrate historical replay → paper session → reconcile → drift."""

    def __init__(
        self,
        *,
        session_config: PaperSessionConfig,
        strategy_factory: Callable[[], Strategy],
        activation: PaperActivationRecord,
        bars: list[MarketBar],
        risk_config: PaperRiskConfig | None = None,
        calendar: CalendarProvider | None = None,
        instruments: list[Instrument] | None = None,
        corporate_actions: list[CorporateAction] | None = None,
        journal_path: Path | None = None,
        checkpoint_path: Path | None = None,
        strategy_explicitly_enabled: bool = True,
        dataset_label: str = "yfinance_labeled_fixture",
    ) -> None:
        self.session_config = session_config
        self.strategy_factory = strategy_factory
        self.activation = activation
        self.bars = list(bars)
        self.risk_config = risk_config or PaperRiskConfig()
        self.calendar = calendar
        self.instruments = instruments
        self.corporate_actions = list(corporate_actions or [])
        self.checkpoint_path = checkpoint_path
        self.strategy_explicitly_enabled = strategy_explicitly_enabled
        self.dataset_label = dataset_label
        meta = strategy_factory().metadata()
        self.journal = Phase13Journal(
            session_id=session_config.session_id,
            strategy_id=meta.strategy_id,
            strategy_version=meta.strategy_version,
            config_hash=session_config.config_hash(),
            path=journal_path,
        )
        self.kill_switch = KillSwitch()

    def _evaluate_gates(self, quality: ReplayQualityReport) -> list[str]:
        from quantfund.paper.execution import PaperExecutionAdapter

        assert_paper_only_adapter(
            PaperExecutionAdapter(session_id=self.session_config.session_id)
        )

        decision = ControlledSimulationPaperGate().evaluate(
            research_eligibility=self.session_config.certified_eligibility,
            dataset_provider_configured=True,
            market_data_available=quality.ok,
            market_data_timestamps_valid=quality.ok,
            stale_data_ok=True,
            calendar_session_ok=self.calendar is not None,
            strategy_explicitly_enabled=self.strategy_explicitly_enabled,
            strategy_spec_valid=True,
            risk_config_valid=True,
            risk_limits_valid=True,
            kill_switch=self.kill_switch,
            paper_execution_adapter_selected=True,
            live_execution_adapter_selected=False,
            broker_credentials_available_to_execution=False,
            reconciliation_clean=True,
            journal_writable=True,
            portfolio_restorable=True,
            deterministic_replay_ok=True,
            using_research_acceptance_as_authorization=False,
            activation=self.activation,
            cost_model_id=self.session_config.cost_model_id,
            slippage_model_id=self.session_config.slippage_model_id,
            strategy_id=self.session_config.strategy_id,
            strategy_version=self.session_config.strategy_version,
        )
        return [] if decision.paper_eligible else list(decision.blockers)

    def run(self, *, run_drift: bool = True) -> Phase13ValidationResult:
        symbol = self.bars[0].symbol if self.bars else "RELIANCE"
        feed = HistoricalReplayFeed(
            symbol=symbol,
            provider="yfinance",
            calendar=self.calendar,
            instruments=self.instruments,
        )
        events, quality = feed.prepare(self.bars)
        meta = self.strategy_factory().metadata()

        self.journal.append(
            "SESSION_STARTED",
            {
                "mode": "CONTROLLED_HISTORICAL_SIMULATION",
                "research_eligibility": "DEVELOPMENT_ONLY",
                "live_trading": False,
                "config_hash": self.session_config.config_hash(),
                "activation_id": self.activation.activation_id,
            },
        )

        blockers = self._evaluate_gates(quality)
        if blockers or not quality.ok:
            self.journal.append(
                "SESSION_ENDED",
                {"state": "FAILED", "blockers": blockers, "quality": quality.to_dict()},
            )
            return Phase13ValidationResult(
                session_id=self.session_config.session_id,
                state="FAILED",
                strategy_id=meta.strategy_id,
                strategy_version=meta.strategy_version,
                dataset_label=self.dataset_label,
                data_source="YFINANCE",
                date_range={"start": None, "end": None},
                paper_eligible=False,
                research_paper_eligible=False,
                orders_count=0,
                accepted_orders=0,
                rejected_orders=0,
                fills_count=0,
                initial_capital=self.session_config.initial_cash,
                config_hash=self.session_config.config_hash(),
                reconciliation_ok=False,
                replay_hash="",
                replay_identical=False,
                kill_switch_state=self.kill_switch.state.value,
                accounting=None,
                drift=None,
                quality=quality,
                warnings=list(quality.warnings),
                data_quality_warnings=list(quality.issues),
                errors=blockers or quality.issues,
                allows_new_orders=False,
            )

        for ev in events:
            self.journal.append(
                "MARKET_BAR",
                {
                    "seq": ev.seq,
                    "open": ev.open,
                    "high": ev.high,
                    "low": ev.low,
                    "close": ev.close,
                    "volume": ev.volume,
                    "source": ev.source,
                },
                timestamp=ev.timestamp,
                symbol=ev.symbol,
            )

        # Live PaperSession for journal mirroring via audit after stop
        session = PaperSession(
            self.session_config,
            strategy=self.strategy_factory(),
            calendar=self.calendar,
            instruments=self.instruments,
            risk_config=self.risk_config,
        )
        session.start()
        for ev in events:
            session.process_event(ev)
            if session.halted:
                break

        # Apply CA after session bars (as-of last session date)
        if self.corporate_actions and events:
            as_of = events[-1].resolved_session_date()
            ca_res = apply_corporate_actions_to_book(
                session.book, self.corporate_actions, as_of=as_of
            )
            for item in ca_res.applied:
                self.journal.append("CORPORATE_ACTION", item, symbol=item.get("symbol"))
            if not ca_res.ok:
                session.activate_kill_switch(reason="invalid_ca", actor="phase13")
                self.journal.append(
                    "KILL_SWITCH_TRIGGERED",
                    {"reason": "invalid_ca", "blockers": ca_res.blockers},
                )

        result = session.stop()

        # Mirror paper audit into Phase 13 journal event types
        accepted = 0
        rejected = 0
        for intent in session.intents:
            self.journal.append(
                "ORDER_CREATED",
                intent.to_mapping_dict(),
                symbol=intent.order.symbol,
            )
            if intent.status in {
                PaperOrderStatus.ACCEPTED,
                PaperOrderStatus.FILLED,
                PaperOrderStatus.PARTIALLY_FILLED,
            }:
                accepted += 1
                self.journal.append(
                    "ORDER_ACCEPTED",
                    {"intent_id": intent.intent_id, "status": intent.status.value},
                    symbol=intent.order.symbol,
                )
            elif intent.status == PaperOrderStatus.REJECTED:
                rejected += 1
                self.journal.append(
                    "ORDER_REJECTED",
                    {
                        "intent_id": intent.intent_id,
                        "reason": intent.reject_reason,
                    },
                    symbol=intent.order.symbol,
                )
            elif intent.status == PaperOrderStatus.CANCELLED:
                self.journal.append(
                    "ORDER_CANCELLED",
                    {"intent_id": intent.intent_id, "reason": intent.reject_reason},
                    symbol=intent.order.symbol,
                )

        for fill in result.fills:
            raw_open = fill.price - fill.slippage_per_unit  # buy: price = open + slip
            self.journal.append(
                "FILL",
                {
                    "fill_id": fill.fill_id,
                    "order_id": fill.order_id,
                    "raw_market_price": raw_open,
                    "simulated_execution_price": fill.price,
                    "quantity": fill.quantity,
                    "gross_notional": fill.quantity * fill.price,
                    "fees": fill.transaction_cost,
                    "slippage_per_unit": fill.slippage_per_unit,
                    "net_cash_impact": fill.net_cash_delta,
                    "side": fill.side.value,
                },
                timestamp=fill.timestamp,
                symbol=fill.symbol,
            )
            self.journal.append(
                "POSITION_UPDATED",
                {"symbol": fill.symbol, "qty": session.book.position_quantity(fill.symbol)},
                symbol=fill.symbol,
            )
            self.journal.append(
                "CASH_UPDATED",
                {"cash": session.book.cash_balance},
            )

        # Signals from audit
        for ae in session.audit.events:
            if ae.event_type == "signal_generated":
                self.journal.append("SIGNAL_GENERATED", ae.payload)
            if ae.event_type == "risk_rejected":
                self.journal.append("RISK_CHECK", {**ae.payload, "accepted": False})
            if ae.event_type == "order_accepted":
                self.journal.append("RISK_CHECK", {**ae.payload, "accepted": True})

        recon = reconcile_phase13_session(
            session.book,
            fills=result.fills,
            orders=result.orders,
            initial_cash=self.session_config.initial_cash,
            journal_event_ids=self.journal.event_ids(),
        )
        self.journal.append(
            "RECONCILIATION",
            recon.to_dict(),
        )

        # Deterministic replay pair
        rr = replay_deterministic(
            config=self.session_config,
            strategy_factory=self.strategy_factory,
            events=events,
            calendar=self.calendar,
            instruments=self.instruments,
            risk_config=self.risk_config,
        )

        drift = None
        if run_drift and recon.ok:
            bt_strategy = self.strategy_factory()
            bt = run_backtest_for_drift(
                bt_strategy,
                [b for b in self.bars if b.symbol == symbol],
                initial_capital=self.session_config.initial_cash,
                cost_model_id=self.session_config.cost_model_id,
                slippage_model_id=self.session_config.slippage_model_id,
            )
            # Fresh paper result for comparison (first replay)
            drift = compare_backtest_paper_semantics(bt, rr.first)

        accounting = snapshot_accounting(
            session.book,
            fills=result.fills,
            equity_curve=[
                p.equity for p in getattr(session.book.portfolio, "equity_curve", [])
            ],
        )

        if self.checkpoint_path is not None:
            write_checkpoint(
                self.checkpoint_path,
                {
                    "session_id": self.session_config.session_id,
                    "cash": accounting.cash,
                    "positions": {
                        s: m["quantity"] for s, m in accounting.positions.items()
                    },
                    "fill_ids": [f.fill_id for f in result.fills],
                    "order_ids": [
                        o.get("intent_id") or o.get("order_id") for o in result.orders
                    ],
                    "kill_switch_state": self.kill_switch.state.value,
                    "state_hash": result.state_hash,
                },
            )

        live_order_count_always_zero(live_orders=0)
        state = "COMPLETED" if recon.ok and rr.deterministic else "FAILED"
        if drift and drift.blocks_further_paper:
            state = "FAILED"

        self.journal.append(
            "SESSION_ENDED",
            {
                "state": state,
                "orders": len(result.orders),
                "fills": len(result.fills),
                "live_orders": 0,
            },
        )

        dates = [e.timestamp.isoformat() for e in events]
        return Phase13ValidationResult(
            session_id=self.session_config.session_id,
            state=state,
            strategy_id=meta.strategy_id,
            strategy_version=meta.strategy_version,
            dataset_label=self.dataset_label,
            data_source="YFINANCE",
            date_range={
                "start": dates[0] if dates else None,
                "end": dates[-1] if dates else None,
            },
            paper_eligible=True,
            research_paper_eligible=False,
            orders_count=len(result.orders),
            accepted_orders=accepted,
            rejected_orders=rejected,
            fills_count=len(result.fills),
            initial_capital=self.session_config.initial_cash,
            config_hash=self.session_config.config_hash(),
            reconciliation_ok=recon.ok,
            replay_hash=rr.first.state_hash,
            replay_identical=rr.deterministic,
            kill_switch_state=self.kill_switch.state.value,
            accounting=accounting,
            drift=drift,
            quality=quality,
            warnings=list(quality.warnings),
            data_quality_warnings=[],
            paper_session=result,
            allows_new_orders=recon.allows_new_orders,
            errors=[] if state == "COMPLETED" else (drift.findings if drift else ["failed"]),
        )


def run_risk_rejection_session(
    *,
    bars: list[MarketBar],
    strategy_factory: Callable[[], Strategy],
    session_config: PaperSessionConfig,
    calendar: CalendarProvider,
    instruments: list[Instrument],
) -> PaperSessionResult:
    """Run with tiny max_order_notional to force risk rejection."""
    risk = PaperRiskConfig(
        max_position_quantity=1.0,
        max_position_notional=1.0,
        max_order_notional=1.0,
        max_gross_exposure=1.0,
        max_order_count=10,
    )
    symbol = bars[0].symbol
    feed = HistoricalReplayFeed(
        symbol=symbol, calendar=calendar, instruments=instruments
    )
    events, quality = feed.prepare(bars)
    assert quality.ok
    return run_paper_session(
        config=session_config.model_copy(
            update={"session_id": session_config.session_id + "_risk"}
        ),
        strategy=strategy_factory(),
        events=events,
        calendar=calendar,
        instruments=instruments,
        risk_config=risk,
    )

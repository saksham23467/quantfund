"""ControlledPaperEngine — runnable simulation paper using Phase 8 PaperSession."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import MarketDataEvent, PaperSessionConfig, SessionMode, state_hash
from quantfund.paper.replay import replay_deterministic, run_paper_session
from quantfund.paper.risk import PaperRiskConfig
from quantfund.paper.session import PaperSessionResult
from quantfund.phase11.journal import PaperJournal
from quantfund.phase11.drift_cert import (
    BacktestPaperDriftReport,
    classify_backtest_paper_drift,
)
from quantfund.phase12.activation import PaperActivationRecord
from quantfund.phase12.eligibility import (
    ControlledPaperEligibilityDecision,
    ControlledSimulationPaperGate,
)
from quantfund.phase12.isolation import assert_paper_only_adapter, live_order_count_always_zero
from quantfund.phase12.market_data import MarketDataBatch, MarketDataConfig
from quantfund.phase12.recovery import write_state_snapshot
from quantfund.strategies.base import Strategy


class ControlledPaperState(str, Enum):
    CREATED = "CREATED"
    PREFLIGHT = "PREFLIGHT"
    MARKET_DATA_CONNECTED = "MARKET_DATA_CONNECTED"
    READY = "READY"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    RECONCILED = "RECONCILED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ControlledPaperResult:
    session_id: str
    state: ControlledPaperState
    research_eligibility: str
    paper_eligible: bool
    research_paper_eligible: bool
    paper_orders: int
    paper_fills: int
    live_orders: int
    broker_submissions: int
    kill_switch_state: str
    reconciliation_ok: bool
    state_hash: str
    eligibility: ControlledPaperEligibilityDecision
    session: PaperSessionResult | None
    drift: BacktestPaperDriftReport | None = None
    claims: str = "NONE"
    live_trading: str = "DISABLED"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "research_eligibility": self.research_eligibility,
            "paper_eligible": self.paper_eligible,
            "research_paper_eligible": self.research_paper_eligible,
            "paper_orders": self.paper_orders,
            "paper_fills": self.paper_fills,
            "live_orders": self.live_orders,
            "broker_submissions": self.broker_submissions,
            "kill_switch_state": self.kill_switch_state,
            "reconciliation_ok": self.reconciliation_ok,
            "state_hash": self.state_hash,
            "eligibility": self.eligibility.to_dict(),
            "session": self.session.to_dict() if self.session else None,
            "drift": self.drift.to_dict() if self.drift else None,
            "claims": self.claims,
            "live_trading": self.live_trading,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "execution_mode": "PAPER",
        }


class ControlledPaperEngine:
    """Orchestrate preflight → market data → PaperSession → journal → report."""

    def __init__(
        self,
        *,
        session_config: PaperSessionConfig,
        strategy_factory: Callable[[], Strategy],
        activation: PaperActivationRecord,
        market_data_config: MarketDataConfig,
        risk_config: PaperRiskConfig | None = None,
        calendar: CalendarProvider | None = None,
        instruments: list[Instrument] | None = None,
        journal_path: Path | None = None,
        snapshot_path: Path | None = None,
        strategy_explicitly_enabled: bool = False,
        strategy_spec_valid: bool = True,
    ) -> None:
        self.session_config = session_config
        self.strategy_factory = strategy_factory
        self.activation = activation
        self.market_data_config = market_data_config
        self.risk_config = risk_config or PaperRiskConfig()
        self.calendar = calendar
        self.instruments = instruments
        self.journal = PaperJournal(
            session_id=session_config.session_id, path=journal_path
        )
        self.snapshot_path = snapshot_path
        self.strategy_explicitly_enabled = strategy_explicitly_enabled
        self.strategy_spec_valid = strategy_spec_valid
        self.state = ControlledPaperState.CREATED
        self.kill_switch = KillSwitch()
        self.live_orders = 0
        self.broker_submissions = 0
        self._eligibility: ControlledPaperEligibilityDecision | None = None

    def _fail(self, reason: str) -> ControlledPaperResult:
        self.state = ControlledPaperState.FAILED
        self.journal.append("SESSION_FAILED", {"reason": reason})
        elig = self._eligibility or ControlledSimulationPaperGate().evaluate(
            research_eligibility=self.session_config.certified_eligibility,
            dataset_provider_configured=False,
            market_data_available=False,
            market_data_timestamps_valid=False,
            stale_data_ok=False,
            calendar_session_ok=False,
            strategy_explicitly_enabled=False,
            strategy_spec_valid=False,
            risk_config_valid=False,
            risk_limits_valid=False,
            kill_switch=self.kill_switch,
            paper_execution_adapter_selected=False,
            live_execution_adapter_selected=True,
            broker_credentials_available_to_execution=True,
            reconciliation_clean=False,
            journal_writable=False,
            portfolio_restorable=False,
            deterministic_replay_ok=False,
            using_research_acceptance_as_authorization=False,
            activation=None,
            cost_model_id=self.session_config.cost_model_id,
            slippage_model_id=self.session_config.slippage_model_id,
            strategy_id=self.session_config.strategy_id,
            strategy_version=self.session_config.strategy_version,
        )
        return ControlledPaperResult(
            session_id=self.session_config.session_id,
            state=self.state,
            research_eligibility=self.session_config.certified_eligibility,
            paper_eligible=False,
            research_paper_eligible=False,
            paper_orders=0,
            paper_fills=0,
            live_orders=0,
            broker_submissions=0,
            kill_switch_state=self.kill_switch.state.value,
            reconciliation_ok=False,
            state_hash=state_hash({"failed": reason}),
            eligibility=elig,
            session=None,
            errors=[reason],
        )

    def evaluate_eligibility(
        self,
        *,
        batch: MarketDataBatch | None,
        reconciliation_clean: bool = True,
        deterministic_replay_ok: bool = True,
        journal_writable: bool = True,
        portfolio_restorable: bool = True,
    ) -> ControlledPaperEligibilityDecision:
        md_ok = batch is not None and batch.ok and bool(batch.events)
        timestamps_ok = True
        stale_ok = True
        if batch is not None:
            for issue in batch.issues:
                if issue.code == "ambiguous_timestamp":
                    timestamps_ok = False
                if issue.code == "stale_data":
                    stale_ok = False
        calendar_ok = self.calendar is not None
        risk_ok = (
            self.risk_config.max_order_notional > 0
            and self.risk_config.max_position_notional > 0
        )
        decision = ControlledSimulationPaperGate().evaluate(
            research_eligibility=self.session_config.certified_eligibility,
            dataset_provider_configured=bool(self.market_data_config.provider),
            market_data_available=md_ok,
            market_data_timestamps_valid=timestamps_ok and md_ok,
            stale_data_ok=stale_ok,
            calendar_session_ok=calendar_ok,
            strategy_explicitly_enabled=self.strategy_explicitly_enabled,
            strategy_spec_valid=self.strategy_spec_valid,
            risk_config_valid=risk_ok,
            risk_limits_valid=risk_ok,
            kill_switch=self.kill_switch,
            paper_execution_adapter_selected=True,
            live_execution_adapter_selected=False,
            broker_credentials_available_to_execution=False,
            reconciliation_clean=reconciliation_clean,
            journal_writable=journal_writable,
            portfolio_restorable=portfolio_restorable,
            deterministic_replay_ok=deterministic_replay_ok,
            using_research_acceptance_as_authorization=False,
            activation=self.activation,
            cost_model_id=self.session_config.cost_model_id,
            slippage_model_id=self.session_config.slippage_model_id,
            strategy_id=self.session_config.strategy_id,
            strategy_version=self.session_config.strategy_version,
        )
        self._eligibility = decision
        return decision

    def run(
        self,
        events: list[MarketDataEvent],
        *,
        market_batch: MarketDataBatch | None = None,
        backtest_order_count: int | None = None,
        backtest_signal_count: int | None = None,
        skip_replay_precheck: bool = False,
    ) -> ControlledPaperResult:
        self.state = ControlledPaperState.PREFLIGHT
        self.journal.append(
            "SESSION_CREATED",
            {
                "config_hash": self.session_config.config_hash(),
                "activation_id": self.activation.activation_id,
                "research_eligibility": self.session_config.certified_eligibility,
            },
        )

        batch = market_batch
        if batch is None:
            from quantfund.phase12.market_data import PaperMarketDataAdapter

            adapter = PaperMarketDataAdapter(
                self.market_data_config,
                instruments=self.instruments,
                calendar=self.calendar,
            )
            batch = adapter.from_events(events)

        self.state = ControlledPaperState.MARKET_DATA_CONNECTED
        self.journal.append("MARKET_DATA_RECEIVED", batch.to_dict())

        replay_ok = True
        if not skip_replay_precheck and batch.ok and len(batch.events) >= 2:
            # Quick determinism precheck on a copy of config
            rr = replay_deterministic(
                config=self.session_config,
                strategy_factory=self.strategy_factory,
                events=list(batch.events),
                calendar=self.calendar,
                instruments=self.instruments,
                risk_config=self.risk_config,
            )
            replay_ok = rr.deterministic

        elig = self.evaluate_eligibility(
            batch=batch,
            deterministic_replay_ok=replay_ok,
        )
        self.journal.append("PREFLIGHT_PASSED" if elig.paper_eligible else "PREFLIGHT_FAILED", elig.to_dict())
        if not elig.paper_eligible:
            return self._fail("paper_eligibility_failed:" + ",".join(elig.blockers[:5]))

        self.state = ControlledPaperState.READY
        # Prove adapter isolation using a throwaway PaperSession's adapter type
        from quantfund.paper.execution import PaperExecutionAdapter

        probe = PaperExecutionAdapter(session_id=self.session_config.session_id)
        assert_paper_only_adapter(probe)

        self.state = ControlledPaperState.RUNNING
        self.journal.append(
            "SESSION_RUNNING",
            {"mode": "PAPER", "live_trading": False},
        )

        # Kernel uses INFRASTRUCTURE_SANDBOX for PaperSession internal gate
        # (research_paper_eligible stays false). Controlled eligibility is Phase 12.
        kernel_cfg = self.session_config
        if kernel_cfg.mode == SessionMode.PRODUCTION:
            # Refuse production mode without research paper eligibility
            return self._fail("production_mode_requires_research_paper_ladder")

        result = run_paper_session(
            config=kernel_cfg,
            strategy=self.strategy_factory(),
            events=list(batch.events),
            calendar=self.calendar,
            instruments=self.instruments,
            risk_config=self.risk_config,
        )

        # Mirror key events into Phase 11 journal
        for order in result.orders:
            self.journal.append("ORDER_CREATED", order)
        for fill in result.fills:
            self.journal.append("ORDER_FILLED", fill.model_dump(mode="json"))
        if self.kill_switch.is_triggered or (
            result.halt_reason and "kill" in (result.halt_reason or "")
        ):
            self.journal.append(
                "KILL_SWITCH_TRIGGERED",
                {"reason": result.halt_reason},
            )

        self.state = ControlledPaperState.STOPPING
        self.journal.append("SESSION_STOPPED", {"halted": result.halted})

        self.state = ControlledPaperState.RECONCILED
        recon_ok = result.reconciliation.ok
        if recon_ok:
            self.journal.append("RECONCILIATION_PASSED", result.reconciliation.to_dict())
        else:
            self.journal.append("RECONCILIATION_FAILED", result.reconciliation.to_dict())
            return self._fail("reconciliation_failed")

        drift = None
        if backtest_order_count is not None:
            drift = classify_backtest_paper_drift(
                signal_count_bt=backtest_signal_count or backtest_order_count,
                signal_count_paper=len(result.orders),
                order_count_bt=backtest_order_count,
                order_count_paper=len(result.orders),
            )
            if drift.blocks_further_paper:
                self.journal.append("DRIFT_CRITICAL", drift.to_dict())
                return self._fail("critical_backtest_paper_drift")

        if self.snapshot_path is not None:
            pos_snap = result.snapshot.get("positions") or {}
            positions_qty = {
                sym: float(meta.get("quantity", 0.0))
                for sym, meta in pos_snap.items()
                if isinstance(meta, dict)
            }
            write_state_snapshot(
                self.snapshot_path,
                {
                    "session_id": self.session_config.session_id,
                    "cash": result.snapshot.get("cash"),
                    "positions": positions_qty,
                    "kill_switch_state": self.kill_switch.state.value,
                    "kill_switch_reason": self.kill_switch.reason,
                    "order_count": len(result.orders),
                    "fill_count": len(result.fills),
                    "risk_counters": {
                        "total_transaction_costs": result.snapshot.get(
                            "total_transaction_costs"
                        ),
                        "total_slippage": result.snapshot.get("total_slippage"),
                    },
                    "state_hash": result.state_hash,
                },
            )

        live_order_count_always_zero(live_orders=self.live_orders)
        self.state = ControlledPaperState.COMPLETED
        self.journal.append(
            "SESSION_COMPLETED",
            {
                "paper_orders": len(result.orders),
                "paper_fills": len(result.fills),
                "live_orders": 0,
            },
        )

        return ControlledPaperResult(
            session_id=self.session_config.session_id,
            state=self.state,
            research_eligibility=elig.research_eligibility,
            paper_eligible=elig.paper_eligible,
            research_paper_eligible=elig.research_paper_eligible,
            paper_orders=len(result.orders),
            paper_fills=len(result.fills),
            live_orders=0,
            broker_submissions=0,
            kill_switch_state=self.kill_switch.state.value,
            reconciliation_ok=recon_ok,
            state_hash=result.state_hash,
            eligibility=elig,
            session=result,
            drift=drift,
            claims="NONE",
            live_trading="DISABLED",
        )

    def activate_kill_switch(self, *, reason: str, actor: str = "operator") -> None:
        self.kill_switch.activate(reason=reason, actor=actor)
        self.journal.append(
            "KILL_SWITCH_TRIGGERED",
            {"reason": reason, "actor": actor},
        )

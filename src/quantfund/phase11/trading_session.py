"""PaperTradingSession — Phase 11 FSM wrapping PaperExecutionAdapter only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from quantfund.paper.execution import ExecutionResult, PaperExecutionAdapter
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.orders import OrderIntent, PaperOrderStatus
from quantfund.paper.portfolio import PaperPortfolio
from quantfund.paper.reconciliation import ReconciliationReport, reconcile_paper_state
from quantfund.paper.risk import PaperRiskDecision, PaperRiskEngine
from quantfund.phase11.connectivity_status import BrokerConnectivityStatus
from quantfund.phase11.isolation import require_paper_execution_adapter
from quantfund.phase11.journal import PaperJournal
from quantfund.phase11.paper_gates import Phase11PaperCertificationGate, Phase11PaperGateDecision
from quantfund.trading.models import Fill


class PaperTradingState(str, Enum):
    CREATED = "CREATED"
    PREFLIGHT = "PREFLIGHT"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    RECONCILING = "RECONCILING"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"


_ALLOWED: dict[PaperTradingState, set[PaperTradingState]] = {
    PaperTradingState.CREATED: {PaperTradingState.PREFLIGHT, PaperTradingState.FAILED},
    PaperTradingState.PREFLIGHT: {PaperTradingState.READY, PaperTradingState.FAILED},
    PaperTradingState.READY: {PaperTradingState.RUNNING, PaperTradingState.FAILED},
    PaperTradingState.RUNNING: {
        PaperTradingState.PAUSED,
        PaperTradingState.STOPPING,
        PaperTradingState.RECONCILING,
        PaperTradingState.FAILED,
    },
    PaperTradingState.PAUSED: {
        PaperTradingState.RUNNING,
        PaperTradingState.STOPPING,
        PaperTradingState.FAILED,
    },
    PaperTradingState.STOPPING: {
        PaperTradingState.RECONCILING,
        PaperTradingState.FAILED,
    },
    PaperTradingState.RECONCILING: {
        PaperTradingState.FINALIZED,
        PaperTradingState.FAILED,
    },
    PaperTradingState.FINALIZED: set(),
    PaperTradingState.FAILED: set(),
}


class IllegalTradingSessionTransition(ValueError):
    pass


@dataclass
class PaperTradingSession:
    """Orchestrates paper trading with hard live isolation."""

    session_id: str
    execution: PaperExecutionAdapter
    risk: PaperRiskEngine
    kill_switch: KillSwitch
    journal: PaperJournal
    portfolio: PaperPortfolio
    connectivity: BrokerConnectivityStatus = BrokerConnectivityStatus.SIMULATED
    state: PaperTradingState = PaperTradingState.CREATED
    gate_decision: Phase11PaperGateDecision | None = None
    allows_new_orders: bool = False
    live_orders: int = 0
    paper_orders: int = 0
    paper_fills: int = 0
    fills: list[Fill] = field(default_factory=list)
    known_order_ids: set[str] = field(default_factory=set)
    history: list[dict[str, Any]] = field(default_factory=list)
    fail_reason: str | None = None
    last_reconcile: ReconciliationReport | None = None
    strategy_enabled: bool = False
    initial_cash: float = 100_000.0

    def __post_init__(self) -> None:
        self.execution = require_paper_execution_adapter(self.execution)
        if self.connectivity == BrokerConnectivityStatus.LIVE:
            raise ValueError("phase11_live_connectivity_forbidden")

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        initial_cash: float = 100_000.0,
        connectivity: BrokerConnectivityStatus = BrokerConnectivityStatus.SIMULATED,
        strategy_enabled: bool = False,
        journal_path=None,
    ) -> PaperTradingSession:
        ks = KillSwitch()
        return cls(
            session_id=session_id,
            execution=PaperExecutionAdapter(session_id=session_id),
            risk=PaperRiskEngine(kill_switch=ks),
            kill_switch=ks,
            journal=PaperJournal(session_id=session_id, path=journal_path),
            portfolio=PaperPortfolio.create(initial_cash),
            connectivity=connectivity,
            strategy_enabled=strategy_enabled,
            initial_cash=initial_cash,
        )

    def _transition(self, target: PaperTradingState, *, reason: str | None = None) -> None:
        if target == PaperTradingState.FAILED:
            if self.state not in {PaperTradingState.FINALIZED, PaperTradingState.FAILED}:
                self.fail_reason = reason or "failed"
                self.state = PaperTradingState.FAILED
                self.allows_new_orders = False
                self.history.append(
                    {
                        "to": target.value,
                        "reason": self.fail_reason,
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                self.journal.append("FAILED", {"reason": self.fail_reason})
            return
        allowed = _ALLOWED.get(self.state, set())
        if target not in allowed:
            raise IllegalTradingSessionTransition(
                f"{self.state.value} -> {target.value} illegal"
            )
        self.state = target
        self.history.append(
            {
                "to": target.value,
                "reason": reason,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.journal.append("STATE", {"state": target.value, "reason": reason})

    def run_preflight_gate(
        self,
        *,
        certified_eligibility: str,
        reconciliation_clean: bool = True,
        **gate_kwargs: Any,
    ) -> Phase11PaperGateDecision:
        self._transition(PaperTradingState.PREFLIGHT, reason="preflight")
        gate = Phase11PaperCertificationGate()
        decision = gate.evaluate(
            certified_eligibility=certified_eligibility,
            connectivity=self.connectivity,
            kill_switch=self.kill_switch,
            reconciliation_clean=reconciliation_clean,
            strategy_explicitly_enabled=self.strategy_enabled,
            paper_mode_explicit=True,
            live_activation_present=False,
            broker_account_known=True,
            **gate_kwargs,
        )
        self.gate_decision = decision
        self.journal.append("ELIGIBILITY", decision.to_dict())
        if not decision.paper_eligible:
            self._transition(
                PaperTradingState.FAILED,
                reason="paper_not_eligible:" + ",".join(decision.blockers[:3]),
            )
            return decision
        self._transition(PaperTradingState.READY, reason="gates_passed")
        return decision

    def start_running(self) -> None:
        if self.state != PaperTradingState.READY:
            raise IllegalTradingSessionTransition("must_be_READY")
        if self.gate_decision is None or not self.gate_decision.paper_eligible:
            self._transition(PaperTradingState.FAILED, reason="not_paper_eligible")
            return
        if self.kill_switch.is_triggered:
            self._transition(PaperTradingState.FAILED, reason="kill_switch")
            return
        if not self.strategy_enabled:
            self._transition(PaperTradingState.FAILED, reason="strategy_disabled")
            return
        self.allows_new_orders = True
        self._transition(PaperTradingState.RUNNING, reason="start")

    def pause(self) -> None:
        self.allows_new_orders = False
        self._transition(PaperTradingState.PAUSED, reason="pause")

    def resume(self) -> None:
        if self.kill_switch.is_triggered:
            self._transition(PaperTradingState.FAILED, reason="kill_switch")
            return
        self.allows_new_orders = True
        self._transition(PaperTradingState.RUNNING, reason="resume")

    def submit_intent(
        self,
        intent: OrderIntent,
        *,
        ref_price: float,
        open_price: float,
        execution_time: datetime,
        market_closed: bool = False,
        stale: bool = False,
    ) -> tuple[PaperRiskDecision, ExecutionResult | None]:
        if self.state != PaperTradingState.RUNNING or not self.allows_new_orders:
            self.journal.append(
                "ORDER_REJECTED",
                {"reason": "session_not_accepting_orders", "state": self.state.value},
            )
            return (
                PaperRiskDecision(False, intent, reason="session_not_accepting_orders"),
                None,
            )
        if self.kill_switch.is_triggered:
            self.allows_new_orders = False
            self.journal.append("ORDER_REJECTED", {"reason": "kill_switch"})
            return PaperRiskDecision(False, intent, reason="kill_switch"), None

        if intent.status == PaperOrderStatus.CREATED:
            intent.transition(PaperOrderStatus.VALIDATED)

        pos = float(self.portfolio.position_quantity(intent.order.symbol))
        exposure = abs(pos) * ref_price
        risk_d = self.risk.check_intent(
            intent,
            ref_price=ref_price,
            current_position_qty=pos,
            current_exposure=exposure,
            current_equity=float(self.portfolio.portfolio.cash) + exposure,
        )
        self.journal.append(
            "RISK_DECISION",
            {"accepted": risk_d.accepted, "reason": risk_d.reason},
        )
        if not risk_d.accepted:
            return risk_d, None

        self.risk.record_accepted(intent, ref_price=ref_price)
        intent.transition(PaperOrderStatus.ACCEPTED)
        self.paper_orders += 1
        self.known_order_ids.add(intent.order.order_id)

        result = self.execution.execute_at_open(
            intent,
            execution_time=execution_time,
            open_price=open_price,
            cash=float(self.portfolio.portfolio.cash),
            position_qty=pos,
            market_closed=market_closed,
            stale=stale,
        )
        self.journal.append(
            "EXECUTION",
            {
                "rejected": result.rejected,
                "reason": result.reason,
                "has_fill": result.fill is not None,
                "execution_mode": "PAPER",
            },
        )
        if not result.rejected and result.fill is not None:
            self.paper_fills += 1
            self.fills.append(result.fill)
            self.portfolio.apply_fill(result.fill)
        assert self.live_orders == 0
        return risk_d, result

    def reconcile(self) -> ReconciliationReport:
        if self.state == PaperTradingState.RUNNING:
            self._transition(PaperTradingState.STOPPING, reason="stop")
        if self.state == PaperTradingState.STOPPING:
            self._transition(PaperTradingState.RECONCILING, reason="reconcile")
        report = reconcile_paper_state(
            self.portfolio,
            fills=list(self.fills),
            initial_cash=self.initial_cash,
            known_order_ids=set(self.known_order_ids),
            audit_fill_ids=self.execution.applied_fill_ids,
        )
        self.last_reconcile = report
        self.journal.append("RECONCILIATION", report.to_dict())
        if not report.ok:
            self.allows_new_orders = False
            if self.state != PaperTradingState.FAILED:
                self._transition(PaperTradingState.FAILED, reason="reconciliation_mismatch")
        return report

    def finalize(self) -> None:
        if self.state == PaperTradingState.RUNNING:
            self._transition(PaperTradingState.STOPPING, reason="finalize")
        if self.state == PaperTradingState.STOPPING:
            self._transition(PaperTradingState.RECONCILING, reason="finalize")
        if self.state == PaperTradingState.RECONCILING:
            if self.last_reconcile is None:
                self.reconcile()
                if self.state == PaperTradingState.FAILED:
                    return
            self._transition(PaperTradingState.FINALIZED, reason="done")
            self.allows_new_orders = False
            self.journal.append(
                "FINALIZED",
                {
                    "execution_mode": "PAPER",
                    "live_orders": self.live_orders,
                    "paper_orders": self.paper_orders,
                    "paper_fills": self.paper_fills,
                    "live_trading": "DISABLED",
                },
            )
            return
        if self.state != PaperTradingState.FINALIZED:
            raise IllegalTradingSessionTransition(
                f"cannot_finalize_from_{self.state.value}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "connectivity": self.connectivity.value,
            "allows_new_orders": self.allows_new_orders,
            "live_orders": self.live_orders,
            "paper_orders": self.paper_orders,
            "paper_fills": self.paper_fills,
            "execution_mode": "PAPER",
            "live_trading": "DISABLED",
            "gate": self.gate_decision.to_dict() if self.gate_decision else None,
            "fail_reason": self.fail_reason,
        }

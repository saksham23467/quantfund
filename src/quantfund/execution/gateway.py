"""ExecutionGateway — thin façade after eligibility / approval / risk.

Phase 9 v1: DRY_RUN + MockBroker only. Zero real orders.
Strategy never imports this module's broker internals for fill creation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from quantfund.execution.audit_live import LiveAuditLog
from quantfund.execution.broker_adapter import (
    BrokerReconcileSnapshot,
    GetOrderRequest,
    ReconcileRequest,
    SubmitOrderRequest,
    assert_mock_only,
)
from quantfund.execution.capabilities import (
    CapabilityError,
    validate_order_capabilities,
)
from quantfund.execution.dry_run import DryRunTransport
from quantfund.execution.live_eligibility import (
    LiveAuthorization,
    LiveEligibilityDecision,
    LiveTradingEligibilityGate,
)
from quantfund.execution.live_orders import (
    BrokerOrderState,
    IdempotencyRecord,
    IdempotencyStore,
    make_client_order_id,
)
from quantfund.execution.live_risk import (
    PLATFORM_SAFETY_LIMITS,
    CapitalLimits,
    LiveRiskEngine,
)
from quantfund.execution.mock_broker import MockBehavior, MockBrokerAdapter
from quantfund.execution.operator_approval import OperatorApprovalGate
from quantfund.execution.reconciliation_live import (
    LiveReconcileReport,
    reconcile_live_state,
)
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.orders import OrderIntent
from quantfund.trading.models import Order, OrderSide, OrderType


class ExecutionMode(str, Enum):
    DRY_RUN = "DRY_RUN"
    # LIVE_SEND intentionally absent / forbidden in Phase 9 v1


@dataclass
class GatewayConfig:
    session_id: str
    mode: ExecutionMode = ExecutionMode.DRY_RUN
    broker_adapter_id: str = "mock"
    certified_eligibility: str = "development_only"
    research_accepted: bool = False
    acceptance_evidence_id: str | None = None
    sealed_test_ok: bool = False
    robustness_ok: bool = False
    paper_eligible: bool = False
    paper_evidence_id: str | None = None
    paper_reconciliation_passed: bool = False
    strategy_id: str | None = None
    mock_behavior: MockBehavior = MockBehavior.FILL
    initial_cash: float = 100_000.0
    strategy_limits: CapitalLimits = field(
        default_factory=lambda: CapitalLimits(
            max_order_notional=50_000,
            max_position_notional=50_000,
            max_gross_exposure=50_000,
            max_capital_allocation=50_000,
        )
    )
    session_limits: CapitalLimits = field(
        default_factory=lambda: CapitalLimits(
            max_order_notional=75_000,
            max_position_notional=75_000,
            max_gross_exposure=75_000,
            max_capital_allocation=75_000,
        )
    )
    account_limits: CapitalLimits = field(
        default_factory=lambda: CapitalLimits(
            max_order_notional=100_000,
            max_position_notional=100_000,
            max_gross_exposure=100_000,
            max_capital_allocation=100_000,
        )
    )


@dataclass
class GatewaySubmitResult:
    accepted: bool
    client_order_id: str | None
    state: BrokerOrderState | None
    reason: str | None
    dry_run: bool
    response: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "client_order_id": self.client_order_id,
            "state": self.state.value if self.state else None,
            "reason": self.reason,
            "dry_run": self.dry_run,
        }


class ExecutionGateway:
    """Authorize → approve → validate → DRY_RUN mock submit → reconcile."""

    def __init__(self, config: GatewayConfig) -> None:
        if config.mode != ExecutionMode.DRY_RUN:
            raise ValueError(
                f"phase9_only_dry_run: mode={config.mode!r} forbidden. "
                "LIVE_SEND disabled in Phase 9 v1."
            )
        assert_mock_only(config.broker_adapter_id)

        self.config = config
        self.audit = LiveAuditLog(session_id=config.session_id)
        self.kill_switch = KillSwitch()
        self.idempotency = IdempotencyStore()
        self.operator = OperatorApprovalGate()
        self.eligibility_gate = LiveTradingEligibilityGate()
        self.eligibility: LiveEligibilityDecision | None = None

        self.broker = MockBrokerAdapter(
            initial_cash=config.initial_cash,
            behavior=config.mock_behavior,
        )
        self.transport = DryRunTransport(broker=self.broker)
        self.risk = LiveRiskEngine(
            strategy_limits=config.strategy_limits,
            session_limits=config.session_limits,
            account_limits=config.account_limits,
            platform_limits=PLATFORM_SAFETY_LIMITS,
            kill_switch=self.kill_switch,
        )

        self._started = False
        self._blocked = False
        self._block_reason: str | None = None
        self.internal_positions: dict[str, float] = {}
        self.internal_cash = config.initial_cash
        self.session_capital_used = 0.0
        self._intent_epochs: dict[str, int] = {}

    @property
    def real_orders_sent(self) -> int:
        return 0

    def start(self) -> LiveEligibilityDecision:
        self.eligibility = self.eligibility_gate.evaluate(
            certified_eligibility=self.config.certified_eligibility,
            research_accepted=self.config.research_accepted,
            acceptance_evidence_id=self.config.acceptance_evidence_id,
            sealed_test_ok=self.config.sealed_test_ok,
            robustness_ok=self.config.robustness_ok,
            paper_eligible=self.config.paper_eligible,
            paper_evidence_id=self.config.paper_evidence_id,
            paper_reconciliation_passed=self.config.paper_reconciliation_passed,
            broker_adapter_id=self.config.broker_adapter_id,
            kill_switch_ready=not self.kill_switch.is_triggered,
            allow_live_send=False,
        )
        self.audit.append(
            "eligibility_check",
            self.eligibility.to_dict(),
        )
        if self.eligibility.authorization == LiveAuthorization.LIVE_AUTHORIZED:
            self.audit.append("authorization_granted", self.eligibility.to_dict())
        else:
            self.audit.append("authorization_denied", self.eligibility.to_dict())

        health = self.broker.connect()
        self.audit.append(
            "broker_connected" if health.connected else "broker_disconnected",
            {"adapter_id": self.broker.adapter_id, "connected": health.connected},
        )
        self.audit.append(
            "live_session_started",
            {
                "mode": self.config.mode.value,
                "broker": self.broker.adapter_id,
                "live_eligible": self.eligibility.live_eligible,
                "real_orders_sent": 0,
            },
        )
        self._started = True
        return self.eligibility

    def approve_operator(self, *, operator_id: str, reason: str) -> None:
        rec = self.operator.approve(
            session_id=self.config.session_id,
            operator_id=operator_id,
            reason=reason,
            strategy_id=self.config.strategy_id,
        )
        self.audit.append("operator_approval", rec.to_dict())

    def activate_kill_switch(self, *, reason: str, actor: str = "operator") -> None:
        """FREEZE ONLY — block new orders; do not flatten."""
        self.kill_switch.activate(reason=reason, actor=actor)
        self.audit.append(
            "kill_switch_activated",
            {"reason": reason, "actor": actor, "policy": "freeze_only"},
        )

    def _block(self, reason: str) -> None:
        self._blocked = True
        self._block_reason = reason

    def submit_intent(
        self,
        intent: OrderIntent,
        *,
        ref_price: float,
        require_live_authorized: bool = True,
        require_operator: bool = True,
    ) -> GatewaySubmitResult:
        if not self._started:
            raise RuntimeError("gateway_not_started")
        if self._blocked:
            return GatewaySubmitResult(
                False, None, None, self._block_reason or "blocked", True
            )
        if self.kill_switch.is_triggered:
            self.audit.append(
                "order_validated",
                {"intent_id": intent.intent_id, "rejected": "kill_switch"},
            )
            return GatewaySubmitResult(False, None, None, "kill_switch", True)

        assert self.eligibility is not None
        if require_live_authorized and not self.eligibility.live_eligible:
            return GatewaySubmitResult(
                False, None, None, "live_authorization_blocked", True
            )
        if require_operator and not self.operator.is_approved(self.config.session_id):
            return GatewaySubmitResult(
                False, None, None, "operator_approval_required", True
            )

        order = intent.order
        try:
            validate_order_capabilities(
                self.broker.capabilities(),
                order_type=order.order_type.value,
                side=order.side.value,
                quantity=order.quantity,
            )
        except CapabilityError as exc:
            self.audit.append(
                "capability_rejected",
                {"intent_id": intent.intent_id, "reason": str(exc)},
            )
            return GatewaySubmitResult(False, None, None, str(exc), True)

        if order.order_type != OrderType.MARKET:
            return GatewaySubmitResult(
                False, None, None, "market_only_required", True
            )

        pos = self.internal_positions.get(order.symbol, 0.0)
        exposure = sum(
            q * ref_price for q in self.internal_positions.values()
        )
        risk = self.risk.check_order(
            order,
            ref_price=ref_price,
            position_qty=pos,
            exposure=exposure,
            equity=self.internal_cash + exposure,
            session_capital_used=self.session_capital_used,
            day_start_equity=self.config.initial_cash,
        )
        if not risk.accepted:
            self.audit.append(
                "capital_limit_rejected",
                {"intent_id": intent.intent_id, "reason": risk.reason},
            )
            return GatewaySubmitResult(False, None, None, risk.reason, True)

        can, why = self.idempotency.can_retry(intent.intent_id)
        if not can:
            self.audit.append(
                "unknown_state",
                {"intent_id": intent.intent_id, "reason": why},
            )
            return GatewaySubmitResult(False, None, None, why, True)

        epoch = self._intent_epochs.get(intent.intent_id, 0)
        client_order_id = make_client_order_id(
            session_id=self.config.session_id,
            intent_id=intent.intent_id,
            submit_epoch=epoch,
        )
        # Pre-submit idempotency record
        record = IdempotencyRecord(
            client_order_id=client_order_id,
            intent_id=intent.intent_id,
            session_id=self.config.session_id,
            submit_epoch=epoch,
            state=BrokerOrderState.CREATED,
        )
        self.idempotency.put(record)
        self.audit.append(
            "order_created",
            {
                "client_order_id": client_order_id,
                "intent_id": intent.intent_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
            },
        )

        record.state = BrokerOrderState.SUBMITTED
        self.idempotency.put(record)
        req = SubmitOrderRequest(
            client_order_id=client_order_id,
            symbol=order.symbol,
            instrument_id=order.metadata.get("instrument_id")
            if order.metadata
            else None,
            side=order.side,
            quantity=order.quantity,
            order_type=order.order_type,
            session_id=self.config.session_id,
            intent_id=intent.intent_id,
            idempotency_key=client_order_id,
            ref_price=ref_price,
        )
        self.audit.append(
            "order_submitted",
            {"client_order_id": client_order_id, "dry_run": True},
        )
        resp = self.transport.submit(req)

        record.state = resp.state
        record.broker_order_id = resp.broker_order_id
        record.filled_quantity = resp.filled_quantity
        self.idempotency.put(record)

        if resp.state == BrokerOrderState.UNKNOWN:
            self.audit.append(
                "unknown_state",
                {"client_order_id": client_order_id, "reason": resp.reject_reason},
            )
            # Do not advance epoch; no blind retry
            return GatewaySubmitResult(
                False, client_order_id, resp.state, "unknown_broker_state", True, resp
            )

        if resp.state == BrokerOrderState.REJECTED:
            self.audit.append(
                "broker_rejected",
                {
                    "client_order_id": client_order_id,
                    "reason": resp.reject_reason,
                },
            )
            self._intent_epochs[intent.intent_id] = epoch + 1
            return GatewaySubmitResult(
                False, client_order_id, resp.state, resp.reject_reason, True, resp
            )

        self.audit.append(
            "broker_acknowledged",
            {
                "client_order_id": client_order_id,
                "broker_order_id": resp.broker_order_id,
                "state": resp.state.value,
            },
        )
        self.audit.append(
            "broker_state_transition",
            {
                "client_order_id": client_order_id,
                "state": resp.state.value,
                "filled_quantity": resp.filled_quantity,
            },
        )

        if resp.filled_quantity > 0:
            self.audit.append(
                "fill_received",
                {
                    "client_order_id": client_order_id,
                    "filled_quantity": resp.filled_quantity,
                    "avg_price": resp.avg_price,
                    "dry_run": True,
                },
            )
            self._apply_internal_fill(
                order, filled=resp.filled_quantity, price=resp.avg_price or ref_price
            )
            self.risk.record_accepted(notional=resp.filled_quantity * ref_price)

        if resp.state in {BrokerOrderState.FILLED, BrokerOrderState.PARTIALLY_FILLED}:
            self._intent_epochs[intent.intent_id] = epoch + 1

        return GatewaySubmitResult(
            True, client_order_id, resp.state, None, True, resp
        )

    def submit_order(
        self,
        order: Order,
        *,
        intent_id: str,
        ref_price: float,
        require_live_authorized: bool = True,
        require_operator: bool = True,
    ) -> GatewaySubmitResult:
        """Convenience: wrap bare Order as intent-like submit."""
        from quantfund.paper.orders import OrderIntent, PaperOrderStatus

        intent = OrderIntent(
            intent_id=intent_id,
            session_id=self.config.session_id,
            order=order,
            status=PaperOrderStatus.VALIDATED,
        )
        return self.submit_intent(
            intent,
            ref_price=ref_price,
            require_live_authorized=require_live_authorized,
            require_operator=require_operator,
        )

    def _apply_internal_fill(self, order: Order, *, filled: float, price: float) -> None:
        if order.side == OrderSide.BUY:
            self.internal_positions[order.symbol] = (
                self.internal_positions.get(order.symbol, 0.0) + filled
            )
            self.internal_cash -= filled * price
            self.session_capital_used += filled * price
        else:
            self.internal_positions[order.symbol] = (
                self.internal_positions.get(order.symbol, 0.0) - filled
            )
            self.internal_cash += filled * price

    def reconcile(self) -> LiveReconcileReport:
        self.audit.append("reconciliation_started", {})
        snap = self.transport.reconcile(
            ReconcileRequest(session_id=self.config.session_id)
        )
        records: list[IdempotencyRecord] = []
        for intent_ids in self.idempotency._by_intent.values():
            for cid in intent_ids:
                rec = self.idempotency.get(cid)
                if rec:
                    records.append(rec)
        all_views = [
            self.broker.get_order(GetOrderRequest(client_order_id=rec.client_order_id))
            for rec in records
        ]
        enriched = BrokerReconcileSnapshot(
            positions=snap.positions,
            cash=snap.cash,
            open_orders=all_views,
        )
        report = reconcile_live_state(
            internal_records=records,
            broker_snapshot=enriched,
            internal_positions=dict(self.internal_positions),
            internal_cash=self.internal_cash,
        )
        if report.ok:
            self.audit.append("reconciliation_passed", report.to_dict())
        else:
            self.audit.append("reconciliation_failed", report.to_dict())
            self._block("reconciliation_failed")
            self.activate_kill_switch(reason="reconciliation_failed", actor="system")
        return report

    def stop(self) -> dict[str, Any]:
        self.audit.append(
            "live_session_stopped",
            {
                "real_orders_sent": self.real_orders_sent,
                "dry_run_submits": len(self.transport.requests),
                "blocked": self._blocked,
                "live_eligible": bool(
                    self.eligibility and self.eligibility.live_eligible
                ),
                "operator_approved": self.operator.is_approved(self.config.session_id),
            },
        )
        self.broker.disconnect()
        return {
            "mode": self.config.mode.value,
            "broker": self.broker.adapter_id,
            "real_orders_sent": 0,
            "live_eligible": bool(self.eligibility and self.eligibility.live_eligible),
            "operator_approved": self.operator.is_approved(self.config.session_id),
            "authorization": (
                self.eligibility.authorization.value if self.eligibility else None
            ),
        }

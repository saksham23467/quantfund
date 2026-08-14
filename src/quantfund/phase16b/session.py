"""Canary session lifecycle + gated order submission."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import deterministic_id
from quantfund.phase15.models import scrub_secrets
from quantfund.phase15.reconcile import reconcile_positions
from quantfund.phase16b.activation import CanaryActivationRecord
from quantfund.phase16b.broker import (
    ZerodhaCanaryBroker,
    make_broker_order_request,
)
from quantfund.phase16b.flags import LiveTradingFlag, resolve_live_trading_flag
from quantfund.phase16b.gates import (
    GateDecision,
    OrderIntent,
    SessionCounters,
    evaluate_pretrade_gates,
)
from quantfund.phase16b.journal import CanaryJournal
from quantfund.phase16b.limits import CanaryPolicy, policy_from_activation
from quantfund.phase16b.market_data_gate import LiveMarketQuote
from quantfund.phase16b.pnl import DailyPnLTracker


class CanarySessionState(str, Enum):
    CREATED = "CREATED"
    ACTIVATION_REQUIRED = "ACTIVATION_REQUIRED"
    ACTIVATED = "ACTIVATED"
    RUNNING = "RUNNING"
    HALTED = "HALTED"
    RECONCILING = "RECONCILING"
    CLOSED = "CLOSED"


@dataclass
class CanarySessionResult:
    mode: str
    state: str
    activation: str = "MISSING"
    strategy: str = "UNKNOWN"
    risk: str = "FAIL"
    reconciliation: str = "UNKNOWN"
    kill_switch: str = "ARMED"
    broker_submission: str = "NONE"
    live_orders: int = 0
    simulated_submissions: int = 0
    place_order_calls: int = 0
    research_eligibility: str = "DEVELOPMENT_ONLY"
    live_trading: str = "DISABLED"
    claims: str = "NONE"
    blockers: list[str] = field(default_factory=list)
    last_gate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return scrub_secrets(
            {
                "mode": self.mode,
                "state": self.state,
                "activation": self.activation,
                "strategy": self.strategy,
                "risk": self.risk,
                "reconciliation": self.reconciliation,
                "kill_switch": self.kill_switch,
                "broker_submission": self.broker_submission,
                "live_orders": self.live_orders,
                "simulated_submissions": self.simulated_submissions,
                "place_order_calls": self.place_order_calls,
                "research_eligibility": self.research_eligibility,
                "live_trading": self.live_trading,
                "claims": self.claims,
                "blockers": list(self.blockers),
                "last_gate": self.last_gate,
            }
        )


class CanarySession:
    def __init__(
        self,
        *,
        mode: str = "CANARY_SIMULATION",
        broker: ZerodhaCanaryBroker,
        strategy_id: str,
        strategy_version: str,
        strategy_hash: str,
        config_hash: str,
        activation: CanaryActivationRecord | None = None,
        policy: CanaryPolicy | None = None,
        kill_switch: KillSwitch | None = None,
        live_flag: LiveTradingFlag | None = None,
        journal_path: Path | None = None,
        pnl_path: Path | None = None,
        session_id: str = "phase16b_canary",
    ) -> None:
        if mode not in {"CANARY_SIMULATION", "LIVE_CANARY"}:
            raise ValueError(f"invalid_mode:{mode}")
        self.mode = mode
        self.broker = broker
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.strategy_hash = strategy_hash
        self.config_hash = config_hash
        self.activation = activation
        self.policy = policy or (
            policy_from_activation(activation) if activation else CanaryPolicy()
        )
        self.kill_switch = kill_switch or KillSwitch()
        self.live_flag = live_flag or resolve_live_trading_flag(explicit=False)
        self.state = CanarySessionState.CREATED
        self.journal = CanaryJournal(session_id=session_id, path=journal_path)
        self.pnl = (
            DailyPnLTracker.load(pnl_path) if pnl_path else DailyPnLTracker()
        )
        if pnl_path:
            self.pnl.path = pnl_path
        self.counters = SessionCounters()
        self._kill_disarmed = False
        self._frozen = {
            "strategy_hash": strategy_hash,
            "config_hash": config_hash,
            "strategy_id": strategy_id,
        }
        self._reconciliation = "UNKNOWN"
        self.result = CanarySessionResult(mode=mode, state=self.state.value)

    def _halt(self, reason: str) -> None:
        self.state = CanarySessionState.HALTED
        self._kill_disarmed = False
        if not self.kill_switch.is_triggered:
            self.kill_switch.activate(reason=reason, actor="canary_session")
        self.broker.revoke_submission_authorization()
        self.journal.append("HALTED", {"reason": reason})
        self._sync_result(blockers=[reason])

    def require_activation(self) -> None:
        self.state = CanarySessionState.ACTIVATION_REQUIRED
        self.journal.append("ACTIVATION_REQUIRED", {})
        self._sync_result()

    def activate(self, activation: CanaryActivationRecord) -> list[str]:
        blockers = activation.validate_against(
            strategy_id=self.strategy_id,
            strategy_hash=self.strategy_hash,
            config_hash=self.config_hash,
        )
        self.activation = activation
        self.policy = policy_from_activation(activation)
        if blockers:
            self._halt("activation_invalid")
            self.result.activation = "INVALID"
            self.result.blockers = blockers
            return blockers
        self.state = CanarySessionState.ACTIVATED
        self.result.activation = "VALID"
        self.journal.append("ACTIVATED", activation.to_dict())
        self._sync_result()
        return []

    def disarm_kill_switch(self, *, actor: str, reason: str) -> None:
        """Explicit disarm required for canary — never silent."""
        if self.kill_switch.is_triggered:
            self.kill_switch.reset(reason=reason, actor=actor)
        self._kill_disarmed = True
        self.journal.append(
            "KILL_SWITCH_DISARMED", {"actor": actor, "reason": reason}
        )
        self._sync_result()

    def emergency_kill(self, *, actor: str = "operator", reason: str = "emergency") -> None:
        self.kill_switch.activate(reason=reason, actor=actor)
        self._kill_disarmed = False
        self.broker.revoke_submission_authorization()
        self.state = CanarySessionState.HALTED
        self.journal.append("EMERGENCY_KILL", {"actor": actor, "reason": reason})
        # preserve visibility — reconcile read-only
        try:
            self.state = CanarySessionState.RECONCILING
            self.reconcile()
        finally:
            self.state = CanarySessionState.HALTED
        self._sync_result(blockers=["emergency_kill"])

    def assert_strategy_immutable(self) -> None:
        if (
            self._frozen["strategy_hash"] != self.strategy_hash
            or self._frozen["config_hash"] != self.config_hash
            or self._frozen["strategy_id"] != self.strategy_id
        ):
            self._halt("strategy_mutation")
            raise RuntimeError("no_dynamic_strategy_mutation")

    def reconcile(self, internal_positions: dict[str, float] | None = None) -> str:
        self.state = (
            CanarySessionState.RECONCILING
            if self.state != CanarySessionState.HALTED
            else self.state
        )
        broker_pos = self.broker.get_positions()
        reco = reconcile_positions(
            broker_positions=broker_pos,
            shadow_positions=internal_positions
            if internal_positions is not None
            else dict(self.counters.positions or {}),
            enabled=True,
        )
        self._reconciliation = reco.status
        self.journal.append("RECONCILIATION", reco.to_dict())
        if reco.status == "RECONCILIATION_MISMATCH":
            self._halt("reconciliation_mismatch")
        elif self.state == CanarySessionState.RECONCILING:
            self.state = CanarySessionState.RUNNING
        self._sync_result()
        return reco.status

    def begin_running(self) -> None:
        if self.state is CanarySessionState.ACTIVATED:
            self.state = CanarySessionState.RUNNING
        self._sync_result()

    def evaluate(
        self, intent: OrderIntent, quote: LiveMarketQuote | None
    ) -> GateDecision:
        self.assert_strategy_immutable()
        self.journal.append("SIGNAL", {"intent": intent.__dict__})
        decision = evaluate_pretrade_gates(
            intent,
            live_flag=self.live_flag,
            activation=self.activation,
            policy=self.policy,
            kill_switch=self.kill_switch,
            kill_switch_disarmed_for_canary=self._kill_disarmed,
            reconciliation_clean=self._reconciliation == "CLEAN",
            quote=quote,
            counters=self.counters,
            mode=self.mode,
            require_live_flag=(self.mode == "LIVE_CANARY"),
        )
        self.journal.append("RISK_GATE", decision.to_dict())
        self.result.last_gate = decision.to_dict()
        if not decision.allowed:
            self.result.risk = "FAIL"
            self.result.blockers = list(decision.blockers)
            # Re-arm kill switch on risk/data/reconcile failure classes
            critical = {
                "reconciliation_mismatch",
                "stale_market_data",
                "clock_skew",
                "max_daily_loss",
                "yfinance_rejected_as_live_feed",
            }
            if critical.intersection(decision.blockers):
                self._kill_disarmed = False
                if not self.kill_switch.is_triggered:
                    self.kill_switch.activate(
                        reason="gate_failure:" + ",".join(decision.blockers[:3]),
                        actor="pretrade_gate",
                    )
            self._sync_result()
        else:
            self.result.risk = "PASS"
        return decision

    def submit_if_allowed(
        self, intent: OrderIntent, quote: LiveMarketQuote | None
    ) -> dict[str, Any]:
        """Evaluate gates; call place_order only if ALL pass."""
        if self.state not in {
            CanarySessionState.RUNNING,
            CanarySessionState.ACTIVATED,
        }:
            return {"submitted": False, "reason": f"bad_state:{self.state.value}"}

        decision = self.evaluate(intent, quote)
        if not decision.place_order_authorized:
            # CRITICAL: never call broker.place_order
            return {
                "submitted": False,
                "reason": "gate_blocked",
                "blockers": decision.blockers,
                "place_order_called": False,
            }

        self.broker.authorize_next_submission()
        req = make_broker_order_request(
            intent_id=intent.intent_id
            or deterministic_id("intent", intent.strategy_id, intent.symbol, intent.quantity),
            symbol=intent.symbol,
            side=intent.side,
            quantity=int(intent.quantity),
            order_type=intent.order_type,
            product=intent.product,
            session_id=self.journal.session_id,
        )
        self.journal.append("ORDER_INTENT", {"intent_id": req.execution_intent_id})
        try:
            resp = self.broker.place_order(request=req)
        except Exception as exc:
            self.broker.revoke_submission_authorization()
            self._halt(f"broker_error:{type(exc).__name__}")
            return {"submitted": False, "reason": type(exc).__name__, "place_order_called": True}

        self.journal.append("BROKER_SUBMISSION", scrub_secrets(resp))
        self.counters.orders_today += 1
        price = intent.ref_price or (quote.price if quote else 0)
        self.counters.turnover_today += float(intent.quantity) * price

        # Observe broker status — only book position on confirmed fills
        try:
            status = self.broker.get_order_status(resp["broker_order_id"])
            self.journal.append("ORDER_STATUS", status)
            filled = float(status.get("filled_quantity") or 0)
            if filled > 0:
                self.journal.append("FILL", status)
                if intent.side.upper() == "BUY":
                    self.counters.positions[intent.symbol] = (
                        self.counters.positions.get(intent.symbol, 0.0) + filled
                    )
                else:
                    self.counters.positions[intent.symbol] = (
                        self.counters.positions.get(intent.symbol, 0.0) - filled
                    )
        except Exception as exc:  # noqa: BLE001
            self.journal.append("ORDER_STATUS_ERROR", {"error": type(exc).__name__})

        self._sync_result()
        return {
            "submitted": True,
            "response": resp,
            "place_order_called": True,
            "simulated": self.broker.simulated,
        }

    def close(self) -> CanarySessionResult:
        if self.state not in {CanarySessionState.CLOSED, CanarySessionState.HALTED}:
            try:
                self.reconcile()
            except Exception:  # noqa: BLE001
                pass
        self.state = CanarySessionState.CLOSED
        self.broker.revoke_submission_authorization()
        self.journal.append("CLOSED", {})
        self._sync_result()
        return self.result

    def _sync_result(self, blockers: list[str] | None = None) -> None:
        self.result.state = self.state.value
        self.result.mode = self.mode
        self.result.strategy = (
            "ALLOWLISTED"
            if self.strategy_id in self.policy.strategy_allowlist
            else "BLOCKED"
        )
        self.result.reconciliation = self._reconciliation
        self.result.kill_switch = (
            "TRIGGERED" if self.kill_switch.is_triggered else "ARMED"
        )
        if self.mode == "CANARY_SIMULATION":
            self.result.broker_submission = (
                "SIMULATED" if self.broker.simulated_submissions else "NONE"
            )
            self.result.live_orders = 0
            self.result.live_trading = "DISABLED"
        else:
            self.result.broker_submission = (
                "REAL" if self.broker.live_orders else "NONE"
            )
            self.result.live_orders = self.broker.live_orders
            self.result.live_trading = (
                "ENABLED" if self.live_flag.enabled else "DISABLED"
            )
        self.result.simulated_submissions = self.broker.simulated_submissions
        self.result.place_order_calls = self.broker.place_calls
        self.result.research_eligibility = "DEVELOPMENT_ONLY"
        self.result.claims = "NONE"
        if self.activation and self.result.activation != "INVALID":
            if not self.activation.validate_against(
                strategy_id=self.strategy_id,
                strategy_hash=self.strategy_hash,
                config_hash=self.config_hash,
            ):
                self.result.activation = "VALID"
        if blockers:
            self.result.blockers = list(blockers)

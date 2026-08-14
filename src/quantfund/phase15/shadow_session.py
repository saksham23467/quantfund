"""Phase 15 shadow session — real/sim data + read-only broker, WOULD_* only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import PaperSessionConfig, deterministic_id
from quantfund.paper.risk import PaperRiskConfig
from quantfund.phase14.market_data import RealTimeBar
from quantfund.phase14.shadow import ShadowEngine
from quantfund.phase15.broker_readonly import (
    BrokerWriteForbidden,
    ReadOnlyBrokerAdapter,
    SimulatedReadOnlyBroker,
)
from quantfund.phase15.freeze import (
    FrozenSessionConfig,
    assert_freeze_unchanged,
    freeze_session_config,
)
from quantfund.phase15.health import Phase15Health, should_pause_shadow
from quantfund.phase15.models import (
    OrderReality,
    SessionState,
    WouldOrder,
    scrub_secrets,
)
from quantfund.phase15.providers import CapableMarketDataProvider
from quantfund.phase15.reconcile import ReconciliationResult, reconcile_positions
from quantfund.phase15.session_machine import SessionStateMachine
from quantfund.phase15.validation import RealMarketEventValidator
from quantfund.strategies.base import Strategy


@dataclass
class Phase15ShadowResult:
    would_orders: list[dict[str, Any]] = field(default_factory=list)
    would_fills: list[dict[str, Any]] = field(default_factory=list)
    simulated_orders: list[dict[str, Any]] = field(default_factory=list)
    data_blocked: list[dict[str, Any]] = field(default_factory=list)
    real_orders: int = 0
    broker_submissions: int = 0
    bars_received: int = 0
    bars_blocked: int = 0
    signals: int = 0
    session_state: str = SessionState.CREATED.value
    reconciliation: str = "SKIPPED"
    market_data_mode: str = "SIMULATED"
    live_trading: bool = False
    kill_switch: str = "ARMED"
    research_eligibility: str = "DEVELOPMENT_ONLY"
    claims: str = "NONE"
    place_order_called: int = 0

    def to_dict(self) -> dict[str, Any]:
        return scrub_secrets(
            {
                "would_orders": len(self.would_orders),
                "would_fills": len(self.would_fills),
                "simulated_orders": len(self.simulated_orders),
                "data_blocked": len(self.data_blocked),
                "real_orders": 0,
                "broker_submissions": 0,
                "bars_received": self.bars_received,
                "bars_blocked": self.bars_blocked,
                "signals": self.signals,
                "session_state": self.session_state,
                "reconciliation": self.reconciliation,
                "market_data_mode": self.market_data_mode,
                "live_trading": False,
                "kill_switch": self.kill_switch,
                "research_eligibility": self.research_eligibility,
                "claims": "NONE",
                "place_order_called": self.place_order_called,
            }
        )


class Phase15ShadowSession:
    """Shadow-only session over CapableMarketDataProvider + ReadOnlyBrokerAdapter."""

    LIVE_TRADING = False

    def __init__(
        self,
        *,
        provider: CapableMarketDataProvider,
        strategy_factory: Callable[[], Strategy],
        session_config: PaperSessionConfig,
        calendar: CalendarProvider,
        broker: ReadOnlyBrokerAdapter | None = None,
        instruments: list[Instrument] | None = None,
        risk_config: PaperRiskConfig | None = None,
        journal_path: Path | None = None,
        max_staleness_seconds: float | None = 3600.0,
        daily_bar_mode: bool = True,
        enable_broker_reconcile: bool = True,
        enable_simulated_fills: bool = True,
        frozen: FrozenSessionConfig | None = None,
        validator: RealMarketEventValidator | None = None,
    ) -> None:
        if getattr(broker or SimulatedReadOnlyBroker(), "can_place_orders", True):
            # ReadOnlyBrokerAdapter.can_place_orders is always False
            pass
        self.broker = broker or SimulatedReadOnlyBroker()
        if self.broker.can_place_orders:
            raise BrokerWriteForbidden("broker_can_place_orders_true")
        caps = self.broker.capabilities()
        if caps.place_order or caps.cancel_order or caps.modify_order:
            raise BrokerWriteForbidden("broker_write_capabilities")

        self.provider = provider
        self.strategy_factory = strategy_factory
        self.session_config = session_config
        self.calendar = calendar
        self.instruments = instruments or []
        self.enable_broker_reconcile = enable_broker_reconcile
        self.enable_simulated_fills = enable_simulated_fills
        self.machine = SessionStateMachine()
        self.health = Phase15Health()
        self.result = Phase15ShadowResult(
            market_data_mode=provider.provenance().mode,
        )
        self.kill_switch = KillSwitch()
        self._place_order_called = 0
        self._shadow_positions: dict[str, float] = {}
        self._reco = ReconciliationResult(
            status="SKIPPED", allows_new_shadow_orders=True
        )

        meta = strategy_factory().metadata()
        self.frozen = frozen or freeze_session_config(
            strategy_id=meta.strategy_id,
            strategy_version=meta.strategy_version,
            session_config_hash=session_config.config_hash(),
            dataset_provenance=provider.provenance().provider_id,
            risk_config={
                "max_order_notional": getattr(
                    risk_config, "max_order_notional", None
                ),
            },
        )
        self._current_freeze = self.frozen

        self.validator = validator or RealMarketEventValidator(
            calendar=calendar,
            known_symbols={i.symbol for i in self.instruments}
            if self.instruments
            else None,
            instrument_master=self.instruments or None,
            max_staleness_seconds=max_staleness_seconds,
            daily_bar_mode=daily_bar_mode,
        )

        self.engine = ShadowEngine(
            provider=provider,
            strategy_factory=strategy_factory,
            session_config=session_config,
            calendar=calendar,
            instruments=instruments,
            risk_config=risk_config,
            journal_path=journal_path,
            max_staleness_seconds=max_staleness_seconds,
            daily_bar_mode=daily_bar_mode,
        )
        # Share kill switch
        self.engine.kill_switch = self.kill_switch
        self.engine.risk.kill_switch = self.kill_switch

    def _check_freeze(self) -> None:
        try:
            assert_freeze_unchanged(self.frozen, self._current_freeze)
        except RuntimeError:
            self.machine.transition(SessionState.SESSION_INVALIDATED)
            self.result.session_state = self.machine.state.value
            self.health.paused = True
            self.engine.allows_new_orders = False

    def invalidate_if_config_changed(self, new_freeze: FrozenSessionConfig) -> None:
        self._current_freeze = new_freeze
        self._check_freeze()

    def preflight(self) -> dict[str, Any]:
        self.machine.transition(SessionState.PREFLIGHT)
        issues: list[str] = []
        if self.LIVE_TRADING:
            issues.append("live_trading_must_be_false")
        if self.broker.can_place_orders:
            issues.append("broker_can_place_orders")
        try:
            # getattr avoids a static place_order call graph; still proves refusal
            write = getattr(self.broker, "place_order")
            write()
            self._place_order_called += 1
            issues.append("place_order_succeeded")
        except BrokerWriteForbidden:
            pass
        ok = not issues
        if not ok:
            self.machine.transition(SessionState.FAILED_SAFE)
        self.result.session_state = self.machine.state.value
        return {
            "ok": ok,
            "issues": issues,
            "live_trading": False,
            "broker_can_place_orders": False,
            "market_data_mode": self.provider.provenance().mode,
            "research_eligibility": "DEVELOPMENT_ONLY",
        }

    def connect(self) -> None:
        if self.machine.state is SessionState.CREATED:
            self.preflight()
        if self.machine.state is SessionState.FAILED_SAFE:
            return
        if self.machine.state is SessionState.PREFLIGHT:
            self.machine.transition(SessionState.CONNECTED)
        self.provider.connect()
        self.broker.connect()
        self.health.provider_connected = True
        self.health.broker_readonly_connected = True
        self.engine.start(list({i.symbol for i in self.instruments} or ["RELIANCE"]))
        self.machine.transition(SessionState.WARMING_UP)
        self.result.session_state = self.machine.state.value

    def begin_shadow(self) -> None:
        if self.machine.state is SessionState.WARMING_UP:
            self.machine.transition(SessionState.RUNNING_SHADOW)
        self._reconcile()
        self.result.session_state = self.machine.state.value

    def pause(self, reason: str = "operator") -> None:
        if self.machine.allows_shadow_decisions or self.machine.state is SessionState.WARMING_UP:
            self.machine.transition(SessionState.PAUSED)
        self.health.paused = True
        self.health.detail.append(reason)
        self.engine.allows_new_orders = False
        self.result.session_state = self.machine.state.value

    def resume(self) -> None:
        if self.machine.state is SessionState.PAUSED and self._reco.allows_new_shadow_orders:
            self.health.paused = False
            self.machine.transition(SessionState.RUNNING_SHADOW)
            self.result.session_state = self.machine.state.value

    def stop(self) -> None:
        if not self.machine.is_terminal:
            if self.machine.state not in {
                SessionState.STOPPING,
                SessionState.SESSION_INVALIDATED,
            }:
                try:
                    self.machine.transition(SessionState.STOPPING)
                except ValueError:
                    self.machine.transition(SessionState.FAILED_SAFE)
            if self.machine.state is SessionState.STOPPING:
                self.machine.transition(SessionState.COMPLETED)
            elif self.machine.state is SessionState.SESSION_INVALIDATED:
                self.machine.transition(SessionState.STOPPING)
                self.machine.transition(SessionState.COMPLETED)
        self.engine.stop()
        self.broker.disconnect()
        self.provider.disconnect()
        self.result.session_state = self.machine.state.value
        self.result.kill_switch = (
            "TRIGGERED" if self.kill_switch.is_triggered else "ARMED"
        )
        self.result.place_order_called = self._place_order_called
        self.result.real_orders = 0
        self.result.broker_submissions = 0

    def activate_kill_switch(self, *, reason: str, actor: str = "operator") -> None:
        self.kill_switch.activate(reason=reason, actor=actor)
        self.engine.activate_kill_switch(reason=reason, actor=actor)
        self.pause(reason="kill_switch")

    def _reconcile(self) -> ReconciliationResult:
        broker_pos = None
        if self.enable_broker_reconcile:
            try:
                broker_pos = self.broker.get_positions()
            except Exception:
                self.health.broker_readonly_connected = False
                self.pause("broker_read_failure")
                broker_pos = {}
        self._reco = reconcile_positions(
            broker_positions=broker_pos if self.enable_broker_reconcile else None,
            shadow_positions=self._shadow_positions,
            enabled=self.enable_broker_reconcile,
        )
        self.result.reconciliation = self._reco.status
        self.health.reconciliation_ok = self._reco.status != "RECONCILIATION_MISMATCH"
        if not self._reco.allows_new_shadow_orders:
            self.engine.allows_new_orders = False
            self.pause("reconciliation_mismatch")
        return self._reco

    def process_bar(self, bar: RealTimeBar) -> dict[str, Any]:
        self._check_freeze()
        self.result.bars_received += 1
        self.health.last_event_timestamp = bar.timestamp
        self.health.event_latency_seconds = bar.data_age_seconds
        self.health.provider_connected = self.provider.health().connected

        if self.kill_switch.is_triggered:
            return {"status": "KILL_SWITCH", "decision": None}

        if should_pause_shadow(self.health) or not self.machine.allows_shadow_decisions:
            if self.machine.state is SessionState.WARMING_UP:
                # allow warm-up ingest without decisions — still validate
                pass
            elif not self.machine.allows_shadow_decisions:
                return {"status": "PAUSED", "decision": None}

        v = self.validator.validate(bar)
        if not v.ok:
            self.result.bars_blocked += 1
            rec = {
                "status": "DATA_BLOCKED",
                "reason": v.blocked_reason,
                "issues": [i.code for i in v.issues],
                "symbol": bar.symbol,
                "timestamp": bar.timestamp.isoformat() if bar.timestamp else None,
            }
            self.result.data_blocked.append(rec)
            self.engine.journal.append("DATA_BLOCKED", scrub_secrets(rec))
            if v.blocked_reason == "stale_data":
                self.health.stale_duration_seconds = bar.data_age_seconds or 0.0
            if v.blocked_reason in {
                "future_timestamp",
                "clock_anomaly",
            }:
                self.health.clock_ok = False
                self.pause("clock_anomaly")
            return rec

        # Warm-up → running
        if self.machine.state is SessionState.WARMING_UP:
            self.begin_shadow()

        if not self._reco.allows_new_shadow_orders:
            return {"status": "RECONCILIATION_MISMATCH", "decision": None}

        before_wo = len(self.engine.result.would_orders)
        before_wf = len(self.engine.result.would_fills)
        self.engine.process(bar)
        self.result.signals = self.engine.result.signals

        # Lift new would-orders into typed WouldOrder + optional SIMULATED_ORDER
        for wo in self.engine.result.would_orders[before_wo:]:
            decision = WouldOrder(
                decision_id=deterministic_id(
                    "p15",
                    wo.get("symbol", ""),
                    wo.get("exec_seq", 0),
                    self.frozen.strategy_hash,
                ),
                strategy_id=self.frozen.strategy_id,
                instrument_id=f"NSE:{wo.get('symbol')}",
                side=str(wo.get("side")),
                quantity=float(wo.get("quantity") or 0),
                intended_price=float(bar.close),
                timestamp=bar.timestamp,
                reason="shadow_risk_accepted",
                risk_result="ACCEPT",
                market_data_version=self.provider.provenance().provider_id,
                strategy_hash=self.frozen.strategy_hash,
                reality=OrderReality.WOULD_ORDER,
                symbol=str(wo.get("symbol")),
                exec_seq=wo.get("exec_seq"),
            )
            d = decision.to_dict()
            self.result.would_orders.append(d)
            self.engine.journal.append("WOULD_ORDER", scrub_secrets(d))
            if self.enable_simulated_fills:
                sim = {
                    **d,
                    "type": OrderReality.SIMULATED_ORDER.value,
                }
                self.result.simulated_orders.append(sim)

            # track shadow position for reconcile (would-fill assumption)
            sym = str(wo.get("symbol"))
            qty = float(wo.get("quantity") or 0)
            side = str(wo.get("side", "")).upper()
            delta = qty if "BUY" in side else -qty
            self._shadow_positions[sym] = self._shadow_positions.get(sym, 0.0) + delta

        for wf in self.engine.result.would_fills[before_wf:]:
            self.result.would_fills.append(wf)

        # Never call broker place_order
        assert self.result.real_orders == 0
        return {
            "status": "OK",
            "would_orders": len(self.result.would_orders),
            "provenance": self.provider.provenance().to_dict(),
        }

    def drain(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while True:
            bar = self.provider.next_bar()
            if bar is None:
                if not self.provider.health().connected:
                    self.health.provider_connected = False
                    self.health.market_data_heartbeat_ok = False
                    self.pause("provider_disconnect")
                break
            out.append(self.process_bar(bar))
        return out

    def run(self, symbols: list[str] | None = None) -> Phase15ShadowResult:
        if self.machine.state is SessionState.CREATED:
            self.connect()
        if symbols:
            self.provider.subscribe(symbols)
        if self.machine.state is SessionState.WARMING_UP:
            self.begin_shadow()
        self.drain()
        self.stop()
        return self.result

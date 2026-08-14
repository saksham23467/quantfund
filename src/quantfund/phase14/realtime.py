"""Real-time event loop shared by paper and shadow modes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.models import Instrument, MarketBar
from quantfund.features.engine import FeatureEngine
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import PaperSessionConfig
from quantfund.phase13.journal import Phase13Journal
from quantfund.phase14.health import HealthStatus, SystemHealth, aggregate_health
from quantfund.phase14.market_data import RealTimeBar, RealTimeMarketDataProvider
from quantfund.phase14.session import orders_allowed, resolve_session_state
from quantfund.strategies.base import Strategy, StrategyContext
from quantfund.trading.models import Signal


class RuntimeMode(str, Enum):
    REAL_TIME_PAPER = "REAL_TIME_PAPER"
    SHADOW = "SHADOW"


@dataclass
class BarProcessResult:
    bar: RealTimeBar
    session_state: str
    stale: bool
    features: dict[str, float | None]
    signal: Signal | None
    allows_new_orders: bool
    health: SystemHealth
    extras: dict[str, Any] = field(default_factory=dict)


class RealTimeEngineBase:
    """Common connect/subscribe/feature/session/freshness logic."""

    def __init__(
        self,
        *,
        mode: RuntimeMode,
        provider: RealTimeMarketDataProvider,
        strategy_factory: Callable[[], Strategy],
        session_config: PaperSessionConfig,
        calendar: CalendarProvider,
        instruments: list[Instrument] | None = None,
        journal_path: Path | None = None,
        max_staleness_seconds: float | None = 3600.0,
        daily_bar_mode: bool = True,
        feature_requests: list[dict[str, Any]] | None = None,
    ) -> None:
        self.mode = mode
        self.provider = provider
        self.strategy_factory = strategy_factory
        self.strategy = strategy_factory()
        self.session_config = session_config
        self.calendar = calendar
        self.instruments = instruments or []
        self.max_staleness_seconds = max_staleness_seconds
        self.daily_bar_mode = daily_bar_mode
        meta = self.strategy.metadata()
        self.journal = Phase13Journal(
            session_id=session_config.session_id,
            strategy_id=meta.strategy_id,
            strategy_version=meta.strategy_version,
            config_hash=session_config.config_hash(),
            path=journal_path,
        )
        self.kill_switch = KillSwitch()
        self.history: list[MarketBar] = []
        self.bars_received = 0
        self.bars_rejected = 0
        self.signals = 0
        self.stale_events = 0
        self.reconciliation_ok = True
        self.allows_new_orders = True
        self._halted_session = False
        self.feature_engine = FeatureEngine()
        self.feature_engine.configure(
            feature_requests
            or [
                {"name": "sma", "window": 3},
                {"name": "momentum", "window": 3},
            ]
        )
        self._last_health = SystemHealth(
            overall=HealthStatus.BLOCKED, allows_new_orders=False
        )

    def start(self, symbols: list[str]) -> None:
        self.provider.connect()
        self.provider.subscribe(symbols)
        self.journal.append(
            "SESSION_STARTED",
            {
                "mode": self.mode.value,
                "research_eligibility": "DEVELOPMENT_ONLY",
                "live_trading": False,
                "broker_submissions": 0,
                "data_source": "YFINANCE_SIMULATED_STREAM",
            },
        )

    def stop(self) -> None:
        self.provider.disconnect()
        self.journal.append(
            "SESSION_ENDED",
            {
                "mode": self.mode.value,
                "bars_received": self.bars_received,
                "bars_rejected": self.bars_rejected,
                "signals": self.signals,
                "live_orders": 0,
            },
        )

    def activate_kill_switch(self, *, reason: str, actor: str = "operator") -> None:
        self.kill_switch.activate(reason=reason, actor=actor)
        self.allows_new_orders = False
        self.journal.append(
            "KILL_SWITCH_TRIGGERED", {"reason": reason, "actor": actor}
        )

    def _compute_features(self, as_of: datetime) -> dict[str, float | None]:
        if not self.history:
            return {}
        try:
            frame = self.feature_engine.compute(self.history)
            return frame.asof(as_of, symbol=self.history[-1].symbol)
        except Exception:
            return {}

    def _health(
        self, *, data_ok: bool, data_stale: bool, session_ok: bool
    ) -> SystemHealth:
        h = aggregate_health(
            data_ok=data_ok,
            data_stale=data_stale,
            engine_ok=True,
            risk_ok=not self.kill_switch.is_triggered,
            journal_ok=True,
            reconciliation_ok=self.reconciliation_ok,
            kill_switch_armed=not self.kill_switch.is_triggered,
            kill_switch_triggered=self.kill_switch.is_triggered,
            session_orders_allowed=session_ok,
        )
        self._last_health = h
        self.allows_new_orders = h.allows_new_orders
        return h

    def ingest_bar(self, bar: RealTimeBar) -> BarProcessResult:
        self.bars_received += 1
        self.journal.append(
            "MARKET_DATA_RECEIVED", bar.to_dict(), timestamp=bar.timestamp, symbol=bar.symbol
        )

        # Chronological guard
        if self.history and bar.timestamp < self.history[-1].timestamp:
            self.bars_rejected += 1
            h = self._health(data_ok=False, data_stale=False, session_ok=False)
            return BarProcessResult(
                bar=bar,
                session_state="HALTED",
                stale=False,
                features={},
                signal=None,
                allows_new_orders=False,
                health=h,
                extras={"rejected": "out_of_order"},
            )

        stale = bar.is_stale(self.max_staleness_seconds)
        if stale:
            self.stale_events += 1
            self.journal.append(
                "MARKET_DATA_STALE",
                {"age": bar.data_age_seconds, "max": self.max_staleness_seconds},
                symbol=bar.symbol,
            )

        state = resolve_session_state(
            bar.timestamp,
            self.calendar,
            halted=self._halted_session,
            daily_bar_mode=self.daily_bar_mode,
        )
        session_ok = orders_allowed(state)

        mb = bar.to_market_bar()
        self.history.append(mb)
        # Future-data isolation: history only ≤ T
        for hbar in self.history:
            if hbar.timestamp > bar.timestamp:
                raise RuntimeError("future_bar_in_history")

        features = self._compute_features(bar.timestamp)
        self.journal.append(
            "FEATURES_COMPUTED",
            {"features": features, "as_of": bar.timestamp.isoformat()},
            timestamp=bar.timestamp,
            symbol=bar.symbol,
        )

        h = self._health(
            data_ok=True, data_stale=stale, session_ok=session_ok and not stale
        )

        signal = None
        if not stale and session_ok and not self.kill_switch.is_triggered:
            ctx = StrategyContext(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                history=list(self.history),
                position_quantity=self._position_qty(bar.symbol),
                cash=self._cash(),
                features=features,
                membership="TRUE",
            )
            signal = self.strategy.generate_signal(ctx)
            self.signals += 1
            self.journal.append(
                "SIGNAL_GENERATED",
                {
                    "action": signal.action.value,
                    "target_quantity": signal.target_quantity,
                    "timestamp": signal.timestamp.isoformat(),
                },
                timestamp=bar.timestamp,
                symbol=bar.symbol,
            )

        return BarProcessResult(
            bar=bar,
            session_state=state.value,
            stale=stale,
            features=features,
            signal=signal,
            allows_new_orders=h.allows_new_orders,
            health=h,
        )

    def _position_qty(self, symbol: str) -> float:
        return 0.0

    def _cash(self) -> float:
        return self.session_config.initial_cash

    def health(self) -> SystemHealth:
        return self._last_health

    def drain(self) -> list[BarProcessResult]:
        """Pull all available bars from the provider."""
        out: list[BarProcessResult] = []
        while True:
            bar = self.provider.next_bar()
            if bar is None:
                break
            out.append(self.process(bar))
        return out

    def process(self, bar: RealTimeBar) -> BarProcessResult:
        """Override in paper/shadow for order handling."""
        return self.ingest_bar(bar)

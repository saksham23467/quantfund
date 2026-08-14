"""Phase 15 health monitoring — pause shadow on critical failure."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from quantfund.phase14.health import HealthStatus, SystemHealth, aggregate_health


@dataclass
class Phase15Health:
    market_data_heartbeat_ok: bool = True
    last_event_timestamp: datetime | None = None
    event_latency_seconds: float | None = None
    stale_duration_seconds: float = 0.0
    provider_connected: bool = False
    broker_readonly_connected: bool = False
    strategy_heartbeat_ok: bool = True
    risk_heartbeat_ok: bool = True
    reconciliation_ok: bool = True
    journal_ok: bool = True
    disk_ok: bool = True
    clock_ok: bool = True
    paused: bool = False
    detail: list[str] = field(default_factory=list)

    @property
    def critical_ok(self) -> bool:
        return all(
            [
                self.market_data_heartbeat_ok,
                self.provider_connected or self.paused,
                self.strategy_heartbeat_ok,
                self.risk_heartbeat_ok,
                self.reconciliation_ok,
                self.journal_ok,
                self.disk_ok,
                self.clock_ok,
            ]
        )

    def to_system_health(self) -> SystemHealth:
        return aggregate_health(
            data_ok=self.market_data_heartbeat_ok and self.provider_connected,
            data_stale=self.stale_duration_seconds > 0,
            engine_ok=self.strategy_heartbeat_ok,
            risk_ok=self.risk_heartbeat_ok,
            journal_ok=self.journal_ok and self.disk_ok,
            reconciliation_ok=self.reconciliation_ok,
            kill_switch_armed=True,
            kill_switch_triggered=False,
            session_orders_allowed=self.critical_ok and not self.paused,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_data_heartbeat_ok": self.market_data_heartbeat_ok,
            "last_event_timestamp": (
                self.last_event_timestamp.isoformat()
                if self.last_event_timestamp
                else None
            ),
            "event_latency_seconds": self.event_latency_seconds,
            "stale_duration_seconds": self.stale_duration_seconds,
            "provider_connected": self.provider_connected,
            "broker_readonly_connected": self.broker_readonly_connected,
            "strategy_heartbeat_ok": self.strategy_heartbeat_ok,
            "risk_heartbeat_ok": self.risk_heartbeat_ok,
            "reconciliation_ok": self.reconciliation_ok,
            "journal_ok": self.journal_ok,
            "disk_ok": self.disk_ok,
            "clock_ok": self.clock_ok,
            "paused": self.paused,
            "critical_ok": self.critical_ok,
            "overall": self.to_system_health().overall.value,
            "detail": list(self.detail),
            "as_of": datetime.now(timezone.utc).isoformat(),
        }


def should_pause_shadow(health: Phase15Health) -> bool:
    return not health.critical_ok or health.paused

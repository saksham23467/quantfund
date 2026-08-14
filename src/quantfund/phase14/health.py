"""Phase 14 component health aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass
class SystemHealth:
    overall: HealthStatus
    components: list[ComponentHealth] = field(default_factory=list)
    allows_new_orders: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall.value,
            "allows_new_orders": self.allows_new_orders,
            "components": [c.to_dict() for c in self.components],
        }


def aggregate_health(
    *,
    data_ok: bool,
    data_stale: bool,
    engine_ok: bool,
    risk_ok: bool,
    journal_ok: bool,
    reconciliation_ok: bool,
    kill_switch_armed: bool,
    kill_switch_triggered: bool,
    session_orders_allowed: bool,
) -> SystemHealth:
    comps = [
        ComponentHealth(
            "data",
            HealthStatus.BLOCKED
            if not data_ok
            else (HealthStatus.DEGRADED if data_stale else HealthStatus.HEALTHY),
            "stale" if data_stale else ("ok" if data_ok else "down"),
        ),
        ComponentHealth(
            "engine",
            HealthStatus.HEALTHY if engine_ok else HealthStatus.BLOCKED,
        ),
        ComponentHealth(
            "risk",
            HealthStatus.HEALTHY if risk_ok else HealthStatus.BLOCKED,
        ),
        ComponentHealth(
            "journal",
            HealthStatus.HEALTHY if journal_ok else HealthStatus.BLOCKED,
        ),
        ComponentHealth(
            "reconciliation",
            HealthStatus.HEALTHY if reconciliation_ok else HealthStatus.BLOCKED,
        ),
        ComponentHealth(
            "kill_switch",
            HealthStatus.BLOCKED
            if kill_switch_triggered
            else (HealthStatus.HEALTHY if kill_switch_armed else HealthStatus.DEGRADED),
            "TRIGGERED" if kill_switch_triggered else "ARMED",
        ),
    ]
    if any(c.status == HealthStatus.BLOCKED for c in comps):
        overall = HealthStatus.BLOCKED
    elif any(c.status == HealthStatus.DEGRADED for c in comps):
        overall = HealthStatus.DEGRADED
    else:
        overall = HealthStatus.HEALTHY

    allows = (
        overall == HealthStatus.HEALTHY
        and session_orders_allowed
        and not data_stale
        and not kill_switch_triggered
        and reconciliation_ok
    )
    return SystemHealth(
        overall=overall, components=comps, allows_new_orders=allows
    )

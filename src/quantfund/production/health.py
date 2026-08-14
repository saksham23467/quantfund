"""Structured production health report — no secrets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from quantfund.execution.modes import QuantFundExecutionMode, resolve_execution_mode_from_env
from quantfund.paper.kill_switch import KillSwitch
from quantfund.production.preflight import PreflightReport


@dataclass
class HealthReport:
    broker: str
    market_data: str
    authentication: str
    execution_mode: str
    risk: str
    reconciliation: str
    kill_switch: str
    strategy: str
    portfolio: str
    last_successful_broker_communication: str | None = None
    last_reconciliation: str | None = None
    open_orders: int = 0
    positions: int = 0
    live_trading: str = "DISABLED"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker": self.broker,
            "market_data": self.market_data,
            "authentication": self.authentication,
            "execution_mode": self.execution_mode,
            "risk": self.risk,
            "reconciliation": self.reconciliation,
            "kill_switch": self.kill_switch,
            "strategy": self.strategy,
            "portfolio": self.portfolio,
            "last_successful_broker_communication": self.last_successful_broker_communication,
            "last_reconciliation": self.last_reconciliation,
            "open_orders": self.open_orders,
            "positions": self.positions,
            "live_trading": self.live_trading,
            "notes": list(self.notes),
        }


def build_health_report(
    *,
    preflight: PreflightReport | None = None,
    kill_switch: KillSwitch | None = None,
    execution_mode: QuantFundExecutionMode | None = None,
    broker_label: str = "zerodha",
    broker_connected: bool = False,
    auth_ok: bool = False,
    market_data_ok: bool = False,
    risk_ok: bool = False,
    reconciliation_clean: bool | None = None,
    strategy_enabled: bool = False,
    portfolio_ok: bool = True,
    open_orders: int = 0,
    positions: int = 0,
    last_broker_ok_at: datetime | None = None,
    last_reconcile_at: datetime | None = None,
    env: dict[str, str] | None = None,
) -> HealthReport:
    mode = execution_mode or resolve_execution_mode_from_env(env)
    ks = kill_switch or KillSwitch()
    recon = (
        "CLEAN"
        if reconciliation_clean is True
        else ("MISMATCH" if reconciliation_clean is False else "UNKNOWN")
    )
    notes = ["Health report never includes secrets.", "Live trading default DISABLED."]
    if preflight is not None and not preflight.ok:
        notes.append(f"preflight_failures={len(preflight.failed)}")
    return HealthReport(
        broker=f"{broker_label}:{'CONNECTED' if broker_connected else 'DISCONNECTED'}",
        market_data="OK" if market_data_ok else "UNAVAILABLE",
        authentication="OK" if auth_ok else "NOT_AUTHENTICATED",
        execution_mode=mode.value,
        risk="OK" if risk_ok else "INVALID_OR_MISSING",
        reconciliation=recon,
        kill_switch="TRIGGERED" if ks.is_triggered else "ARMED",
        strategy="ENABLED" if strategy_enabled else "DISABLED",
        portfolio="OK" if portfolio_ok else "ERROR",
        last_successful_broker_communication=(
            last_broker_ok_at.astimezone(timezone.utc).isoformat()
            if last_broker_ok_at
            else None
        ),
        last_reconciliation=(
            last_reconcile_at.astimezone(timezone.utc).isoformat()
            if last_reconcile_at
            else None
        ),
        open_orders=open_orders,
        positions=positions,
        live_trading="DISABLED",
        notes=notes,
    )


def format_health_report(report: HealthReport) -> str:
    d = report.to_dict()
    lines = ["=== PRODUCTION HEALTH ==="]
    for k, v in d.items():
        if k == "notes":
            continue
        lines.append(f"{k}: {v}")
    lines.append("Notes:")
    for n in report.notes:
        lines.append(f"- {n}")
    return "\n".join(lines)

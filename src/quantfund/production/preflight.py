"""Deterministic production preflight — never places orders."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from quantfund.brokers.intent_store import ExecutionIntentStore
from quantfund.brokers.zerodha.auth import credentials_configured, load_credentials_from_env
from quantfund.execution.modes import QuantFundExecutionMode, resolve_execution_mode_from_env
from quantfund.paper.kill_switch import KillSwitch


class PreflightStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NOT_CONFIGURED = "NOT_CONFIGURED"


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: PreflightStatus
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass
class PreflightReport:
    checks: list[PreflightCheck] = field(default_factory=list)
    orders_attempted: int = 0  # must remain 0
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def ok(self) -> bool:
        return not any(c.status == PreflightStatus.FAIL for c in self.checks)

    @property
    def failed(self) -> list[PreflightCheck]:
        return [c for c in self.checks if c.status == PreflightStatus.FAIL]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "orders_attempted": self.orders_attempted,
            "generated_at": self.generated_at,
            "checks": [c.to_dict() for c in self.checks],
            "warning": "Preflight never places orders.",
        }


@dataclass
class PreflightContext:
    env: dict[str, str] = field(default_factory=dict)
    kill_switch: KillSwitch | None = None
    intent_store: ExecutionIntentStore | None = None
    risk_limits_configured: bool = False
    reconciliation_clean: bool | None = None
    research_eligibility: str = "development_only"
    paper_eligible: bool = False
    strategy_eligible: bool = False
    config_hashes: dict[str, str] = field(default_factory=dict)
    registry_path: Path | None = None
    broker_health_connected: bool | None = None
    broker_permissions_ok: bool | None = None
    instrument_resolved: bool | None = None
    market_session_open: bool | None = None
    outstanding_broker_orders: int = 0
    authenticated_user: str | None = None
    clock_skew_seconds: float | None = None
    connectivity_probe: Callable[[], bool] | None = None


def run_preflight(ctx: PreflightContext | None = None) -> PreflightReport:
    """Run all preflight checks. Never places an order."""
    ctx = ctx or PreflightContext(env=dict(os.environ))
    env = ctx.env or dict(os.environ)
    checks: list[PreflightCheck] = []

    # environment configuration
    mode = resolve_execution_mode_from_env(env)
    checks.append(
        PreflightCheck(
            "environment_configuration",
            PreflightStatus.PASS,
            f"execution_mode={mode.value}",
        )
    )

    # broker credentials
    if credentials_configured(env):
        checks.append(
            PreflightCheck(
                "broker_credentials",
                PreflightStatus.PASS,
                "ZERODHA_* present (values not logged)",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "broker_credentials",
                PreflightStatus.NOT_CONFIGURED,
                "ZERODHA_API_KEY/SECRET not set",
            )
        )

    # API connectivity (optional probe — read-only callback)
    if ctx.connectivity_probe is None:
        if credentials_configured(env):
            checks.append(
                PreflightCheck(
                    "api_connectivity",
                    PreflightStatus.WARN,
                    "credentials present; connectivity not probed in this run",
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    "api_connectivity",
                    PreflightStatus.NOT_CONFIGURED,
                    "no credentials",
                )
            )
    else:
        try:
            ok = bool(ctx.connectivity_probe())
            checks.append(
                PreflightCheck(
                    "api_connectivity",
                    PreflightStatus.PASS if ok else PreflightStatus.FAIL,
                    "probe_ok" if ok else "probe_failed",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                PreflightCheck(
                    "api_connectivity",
                    PreflightStatus.FAIL,
                    f"probe_error:{type(exc).__name__}",
                )
            )

    # authenticated user
    if ctx.authenticated_user:
        checks.append(
            PreflightCheck(
                "authenticated_user_identity",
                PreflightStatus.PASS,
                f"user={ctx.authenticated_user}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "authenticated_user_identity",
                PreflightStatus.NOT_CONFIGURED,
                "profile not fetched",
            )
        )

    # broker API permissions
    if ctx.broker_permissions_ok is None:
        checks.append(
            PreflightCheck(
                "broker_api_permissions",
                PreflightStatus.NOT_CONFIGURED,
                "permissions not verified",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "broker_api_permissions",
                PreflightStatus.PASS if ctx.broker_permissions_ok else PreflightStatus.FAIL,
                "ok" if ctx.broker_permissions_ok else "insufficient_permissions",
            )
        )

    # instrument/token resolution
    if ctx.instrument_resolved is None:
        checks.append(
            PreflightCheck(
                "instrument_token_resolution",
                PreflightStatus.NOT_CONFIGURED,
                "not checked",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "instrument_token_resolution",
                PreflightStatus.PASS if ctx.instrument_resolved else PreflightStatus.FAIL,
                "resolved" if ctx.instrument_resolved else "unresolved",
            )
        )

    # market session
    if ctx.market_session_open is None:
        checks.append(
            PreflightCheck(
                "market_session_status",
                PreflightStatus.WARN,
                "session status unknown",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "market_session_status",
                PreflightStatus.PASS if ctx.market_session_open else PreflightStatus.WARN,
                "open" if ctx.market_session_open else "closed",
            )
        )

    # clock / timezone
    try:
        _ = ZoneInfo("Asia/Kolkata")
        skew = ctx.clock_skew_seconds
        if skew is not None and abs(skew) > 30:
            checks.append(
                PreflightCheck(
                    "system_clock_timezone",
                    PreflightStatus.FAIL,
                    f"clock_skew_seconds={skew}",
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    "system_clock_timezone",
                    PreflightStatus.PASS,
                    "Asia/Kolkata available; skew ok or unchecked",
                )
            )
    except Exception:  # noqa: BLE001
        checks.append(
            PreflightCheck(
                "system_clock_timezone",
                PreflightStatus.FAIL,
                "timezone_unavailable",
            )
        )

    # registry / database
    if ctx.registry_path is None:
        checks.append(
            PreflightCheck(
                "database_registry",
                PreflightStatus.WARN,
                "registry path not provided",
            )
        )
    elif Path(ctx.registry_path).exists():
        checks.append(
            PreflightCheck(
                "database_registry",
                PreflightStatus.PASS,
                str(ctx.registry_path),
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "database_registry",
                PreflightStatus.FAIL,
                "registry_missing",
            )
        )

    # risk configuration
    checks.append(
        PreflightCheck(
            "risk_configuration",
            PreflightStatus.PASS if ctx.risk_limits_configured else PreflightStatus.FAIL,
            "configured" if ctx.risk_limits_configured else "missing",
        )
    )

    # kill switch
    ks = ctx.kill_switch or KillSwitch()
    if ks.is_triggered:
        checks.append(
            PreflightCheck(
                "kill_switch_state",
                PreflightStatus.FAIL,
                f"TRIGGERED:{ks.reason}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "kill_switch_state",
                PreflightStatus.PASS,
                "ARMED",
            )
        )

    # execution mode
    if mode == QuantFundExecutionMode.BROKER_LIVE:
        checks.append(
            PreflightCheck(
                "execution_mode",
                PreflightStatus.WARN,
                "BROKER_LIVE requested — still requires activation gates",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "execution_mode",
                PreflightStatus.PASS,
                f"{mode.value} (default safe if OFF)",
            )
        )

    # research eligibility
    elig = (ctx.research_eligibility or "").lower()
    if elig == "development_only":
        checks.append(
            PreflightCheck(
                "research_eligibility",
                PreflightStatus.WARN,
                "DEVELOPMENT_ONLY — not research-grade",
            )
        )
    elif elig in {"research_eligible", "production_candidate"}:
        checks.append(
            PreflightCheck(
                "research_eligibility",
                PreflightStatus.PASS,
                elig,
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "research_eligibility",
                PreflightStatus.WARN,
                elig or "unknown",
            )
        )

    # paper eligibility
    checks.append(
        PreflightCheck(
            "paper_eligibility",
            PreflightStatus.PASS if ctx.paper_eligible else PreflightStatus.WARN,
            str(ctx.paper_eligible).upper(),
        )
    )

    # strategy eligibility
    checks.append(
        PreflightCheck(
            "strategy_eligibility",
            PreflightStatus.PASS if ctx.strategy_eligible else PreflightStatus.WARN,
            "enabled" if ctx.strategy_eligible else "not_enabled",
        )
    )

    # config hashes
    if ctx.config_hashes:
        checks.append(
            PreflightCheck(
                "required_configuration_hashes",
                PreflightStatus.PASS,
                ",".join(sorted(ctx.config_hashes)),
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "required_configuration_hashes",
                PreflightStatus.WARN,
                "no hashes provided",
            )
        )

    # secrets availability (presence only)
    secret_vars = ("ZERODHA_API_KEY", "ZERODHA_API_SECRET", "ZERODHA_ACCESS_TOKEN")
    present = [k for k in secret_vars if (env.get(k) or "").strip()]
    if len(present) >= 2:
        checks.append(
            PreflightCheck(
                "required_secrets_availability",
                PreflightStatus.PASS,
                f"present_count={len(present)} (values redacted)",
            )
        )
    elif present:
        checks.append(
            PreflightCheck(
                "required_secrets_availability",
                PreflightStatus.WARN,
                "partial secrets",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "required_secrets_availability",
                PreflightStatus.NOT_CONFIGURED,
                "no secrets",
            )
        )

    # reconciliation
    if ctx.reconciliation_clean is None:
        checks.append(
            PreflightCheck(
                "reconciliation_state",
                PreflightStatus.NOT_CONFIGURED,
                "no reconcile run",
            )
        )
    elif ctx.reconciliation_clean:
        checks.append(
            PreflightCheck(
                "reconciliation_state",
                PreflightStatus.PASS,
                "clean",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "reconciliation_state",
                PreflightStatus.FAIL,
                "mismatch",
            )
        )

    # outstanding orders / intents
    checks.append(
        PreflightCheck(
            "outstanding_orders",
            PreflightStatus.PASS if ctx.outstanding_broker_orders == 0 else PreflightStatus.WARN,
            f"count={ctx.outstanding_broker_orders}",
        )
    )
    store = ctx.intent_store or ExecutionIntentStore()
    open_intents = sum(
        1 for r in getattr(store, "_by_intent", {}).values() if r.broker_order_id
    )
    checks.append(
        PreflightCheck(
            "outstanding_execution_intents",
            PreflightStatus.PASS if open_intents == 0 else PreflightStatus.WARN,
            f"count={open_intents}",
        )
    )

    # broker health snapshot
    if ctx.broker_health_connected is None:
        checks.append(
            PreflightCheck(
                "broker_health",
                PreflightStatus.NOT_CONFIGURED,
                "not probed",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "broker_health",
                PreflightStatus.PASS
                if ctx.broker_health_connected
                else PreflightStatus.FAIL,
                "connected" if ctx.broker_health_connected else "disconnected",
            )
        )

    # Never place orders — explicit invariant
    _ = load_credentials_from_env(env)  # presence only
    return PreflightReport(checks=checks, orders_attempted=0)

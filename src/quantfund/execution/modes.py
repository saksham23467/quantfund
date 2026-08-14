"""QuantFund broker execution modes (Phase 9B).

Separate from ExecutionGateway.ExecutionMode (DRY_RUN-only Phase 9 path).
Default is always OFF. BROKER_LIVE requires multiple independent gates.
"""

from __future__ import annotations

import os
from enum import Enum


LIVE_CONFIRM_PHRASE = "I_UNDERSTAND_REAL_MONEY"


class QuantFundExecutionMode(str, Enum):
    OFF = "OFF"
    SIMULATION = "SIMULATION"
    BROKER_SANDBOX = "BROKER_SANDBOX"
    BROKER_LIVE = "BROKER_LIVE"


def parse_execution_mode(raw: str | None) -> QuantFundExecutionMode:
    if raw is None or str(raw).strip() == "":
        return QuantFundExecutionMode.OFF
    key = str(raw).strip().upper()
    try:
        return QuantFundExecutionMode(key)
    except ValueError as exc:
        raise ValueError(f"unknown_execution_mode:{raw!r}") from exc


def resolve_execution_mode_from_env(
    env: dict[str, str] | None = None,
) -> QuantFundExecutionMode:
    e = env if env is not None else os.environ
    return parse_execution_mode(e.get("QUANTFUND_EXECUTION_MODE"))


def live_confirm_ok(env: dict[str, str] | None = None) -> bool:
    e = env if env is not None else os.environ
    return e.get("QUANTFUND_LIVE_TRADING_CONFIRM") == LIVE_CONFIRM_PHRASE


def broker_live_gates_satisfied(
    *,
    mode: QuantFundExecutionMode,
    env: dict[str, str] | None = None,
    risk_limits_configured: bool,
    kill_switch_initialized: bool,
    kill_switch_triggered: bool,
    broker_healthy: bool,
    strategy_broker_approved: bool,
    zerodha_env: str | None,
) -> tuple[bool, list[str]]:
    """Multi-gate check for BROKER_LIVE. Never a single LIVE=true boolean."""
    blockers: list[str] = []
    if mode != QuantFundExecutionMode.BROKER_LIVE:
        blockers.append("mode_not_broker_live")
    if not live_confirm_ok(env):
        blockers.append("live_confirm_phrase_missing")
    if not risk_limits_configured:
        blockers.append("risk_limits_not_configured")
    if not kill_switch_initialized:
        blockers.append("kill_switch_not_initialized")
    if kill_switch_triggered:
        blockers.append("kill_switch_triggered")
    if not broker_healthy:
        blockers.append("broker_unhealthy")
    if not strategy_broker_approved:
        blockers.append("strategy_not_broker_approved")
    if (zerodha_env or "").lower() != "production":
        blockers.append("zerodha_env_not_production")
    return (len(blockers) == 0), blockers

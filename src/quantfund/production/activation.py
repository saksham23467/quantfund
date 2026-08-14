"""Multi-gate live activation — env alone cannot authorize trading."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from quantfund.execution.modes import LIVE_CONFIRM_PHRASE, QuantFundExecutionMode


ACTIVATION_CONFIRM_PHRASE = "I_CONFIRM_CONTROLLED_LIVE_ACTIVATION"


class ActivationGate(str, Enum):
    LIVE_TRADING_ENABLED = "LIVE_TRADING_ENABLED"
    BROKER_CREDENTIALS_VALID = "BROKER_CREDENTIALS_VALID"
    BROKER_CONNECTIVITY_VALID = "BROKER_CONNECTIVITY_VALID"
    PREFLIGHT_VALID = "PREFLIGHT_VALID"
    RECONCILIATION_CLEAN = "RECONCILIATION_CLEAN"
    RISK_CONFIG_VALID = "RISK_CONFIG_VALID"
    HUMAN_CONFIRMATION = "HUMAN_CONFIRMATION"
    STRATEGY_EXPLICITLY_ENABLED = "STRATEGY_EXPLICITLY_ENABLED"
    GLOBAL_KILL_SWITCH_OFF = "GLOBAL_KILL_SWITCH_OFF"


@dataclass(frozen=True)
class GateResult:
    gate: ActivationGate
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate.value,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class ActivationRecord:
    activation_id: str
    timestamp: str
    actor: str
    strategy_id: str
    strategy_hash: str
    config_hash: str
    risk_config_hash: str
    broker_identity: str
    reason: str
    environment: str
    max_order_value: float
    max_daily_loss: float
    confirmation_phrase_used: bool
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "activation_id": self.activation_id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "strategy_id": self.strategy_id,
            "strategy_hash": self.strategy_hash,
            "config_hash": self.config_hash,
            "risk_config_hash": self.risk_config_hash,
            "broker_identity": self.broker_identity,
            "reason": self.reason,
            "environment": self.environment,
            "max_order_value": self.max_order_value,
            "max_daily_loss": self.max_daily_loss,
            "confirmation_phrase_used": self.confirmation_phrase_used,
            "active": self.active,
        }


@dataclass
class ActivationDecision:
    allowed: bool
    gates: list[GateResult] = field(default_factory=list)
    failed_gates: list[str] = field(default_factory=list)
    broker_live_default: str = "DISABLED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "failed_gates": list(self.failed_gates),
            "gates": [g.to_dict() for g in self.gates],
            "broker_live_default": self.broker_live_default,
            "orders_authorized": False if not self.allowed else True,
        }


def evaluate_activation_gates(
    *,
    live_trading_enabled: bool,
    broker_credentials_valid: bool,
    broker_connectivity_valid: bool,
    preflight_valid: bool,
    reconciliation_clean: bool,
    risk_config_valid: bool,
    human_confirmation: bool,
    strategy_explicitly_enabled: bool,
    global_kill_switch_off: bool,
    execution_mode: QuantFundExecutionMode = QuantFundExecutionMode.OFF,
) -> ActivationDecision:
    """ALL gates required. BROKER_LIVE env alone is insufficient."""
    results = [
        GateResult(
            ActivationGate.LIVE_TRADING_ENABLED,
            live_trading_enabled,
            "activation record active" if live_trading_enabled else "no activation record",
        ),
        GateResult(
            ActivationGate.BROKER_CREDENTIALS_VALID,
            broker_credentials_valid,
        ),
        GateResult(
            ActivationGate.BROKER_CONNECTIVITY_VALID,
            broker_connectivity_valid,
        ),
        GateResult(ActivationGate.PREFLIGHT_VALID, preflight_valid),
        GateResult(ActivationGate.RECONCILIATION_CLEAN, reconciliation_clean),
        GateResult(ActivationGate.RISK_CONFIG_VALID, risk_config_valid),
        GateResult(
            ActivationGate.HUMAN_CONFIRMATION,
            human_confirmation,
            "explicit confirmation phrase required (env alone insufficient)",
        ),
        GateResult(
            ActivationGate.STRATEGY_EXPLICITLY_ENABLED,
            strategy_explicitly_enabled,
        ),
        GateResult(
            ActivationGate.GLOBAL_KILL_SWITCH_OFF,
            global_kill_switch_off,
        ),
    ]
    # Mode BROKER_LIVE without activation still fails LIVE_TRADING_ENABLED
    if execution_mode == QuantFundExecutionMode.BROKER_LIVE and not live_trading_enabled:
        results[0] = GateResult(
            ActivationGate.LIVE_TRADING_ENABLED,
            False,
            "BROKER_LIVE mode without activation record",
        )
    failed = [g.gate.value for g in results if not g.passed]
    return ActivationDecision(
        allowed=len(failed) == 0,
        gates=results,
        failed_gates=failed,
    )


def create_activation_record(
    *,
    actor: str,
    confirmation_phrase: str,
    strategy_id: str,
    strategy_hash: str,
    config_hash: str,
    risk_config_hash: str,
    broker_identity: str,
    reason: str,
    environment: str,
    max_order_value: float,
    max_daily_loss: float,
    current_positions: dict[str, float] | None = None,
) -> ActivationRecord:
    """Human confirmation must include the exact phrase — not env-bypassable."""
    if confirmation_phrase != ACTIVATION_CONFIRM_PHRASE:
        raise ValueError("invalid_confirmation_phrase")
    if not actor or not actor.strip():
        raise ValueError("actor_required")
    if not reason or not reason.strip():
        raise ValueError("reason_required")
    if max_order_value <= 0 or max_daily_loss <= 0:
        raise ValueError("risk_limits_must_be_positive")
    _ = current_positions  # required in CLI display; stored via reason context
    now = datetime.now(timezone.utc).isoformat()
    raw = f"{actor}|{strategy_hash}|{config_hash}|{now}|{reason}"
    aid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return ActivationRecord(
        activation_id=aid,
        timestamp=now,
        actor=actor.strip(),
        strategy_id=strategy_id,
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        risk_config_hash=risk_config_hash,
        broker_identity=broker_identity,
        reason=reason.strip(),
        environment=environment,
        max_order_value=float(max_order_value),
        max_daily_loss=float(max_daily_loss),
        confirmation_phrase_used=True,
        active=True,
    )


def write_activation_record(path: Path, record: ActivationRecord) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"activation_record_immutable:{path}")
    path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
    return path


def load_activation_record(path: Path) -> ActivationRecord | None:
    path = Path(path)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return ActivationRecord(**data)


def deactivate_record(path: Path, *, actor: str, reason: str) -> ActivationRecord:
    rec = load_activation_record(path)
    if rec is None:
        raise FileNotFoundError(path)
    data = rec.to_dict()
    data["active"] = False
    data["reason"] = f"DEACTIVATED by {actor}: {reason} | prior: {rec.reason}"
    # overwrite allowed for deactivation only
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return ActivationRecord(**data)


def env_alone_cannot_activate(env: dict[str, str]) -> bool:
    """True if env has LIVE flags but no human confirmation artifact concept."""
    # Even with confirm env phrase, activation requires create_activation_record()
    return bool(
        env.get("QUANTFUND_EXECUTION_MODE") == "BROKER_LIVE"
        or env.get("LIVE_TRADING_ENABLED") == "true"
        or env.get("QUANTFUND_LIVE_TRADING_CONFIRM") == LIVE_CONFIRM_PHRASE
    )

"""Recovery behaviors for Phase 16A broker connectivity failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quantfund.execution.credentials import redact_secrets
from quantfund.paper.kill_switch import KillSwitch


@dataclass
class RecoveryAction:
    trigger: str
    action: str
    allows_live_orders: bool = False
    retry_recommended: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "action": self.action,
            "allows_live_orders": False,
            "retry_recommended": self.retry_recommended,
            "detail": self.detail,
        }


@dataclass
class RecoveryPlan:
    actions: list[RecoveryAction] = field(default_factory=list)
    kill_switch_state: str = "ARMED"
    live_orders: int = 0

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "actions": [a.to_dict() for a in self.actions],
                "kill_switch_state": self.kill_switch_state,
                "live_orders": 0,
                "live_trading": "DISABLED",
            }
        )


def plan_recovery(trigger: str, *, kill_switch: KillSwitch | None = None) -> RecoveryPlan:
    """Map failure modes to fail-closed recovery (never submit orders)."""
    ks = kill_switch or KillSwitch()
    mapping = {
        "api_timeout": RecoveryAction(
            trigger="api_timeout",
            action="DISCONNECT_AND_RETRY_READ_ONLY",
            retry_recommended=True,
            detail="Backoff then re-authenticate; no orders",
        ),
        "authentication_failure": RecoveryAction(
            trigger="authentication_failure",
            action="HALT_READINESS",
            retry_recommended=False,
            detail="Require new session token via env; no orders",
        ),
        "stale_data": RecoveryAction(
            trigger="stale_data",
            action="PAUSE_DECISIONS",
            retry_recommended=True,
            detail="Wait for fresh quotes; block readiness progression",
        ),
        "malformed_broker_response": RecoveryAction(
            trigger="malformed_broker_response",
            action="FAIL_CLOSED",
            retry_recommended=False,
            detail="Do not trust partial state; no orders",
        ),
        "reconciliation_mismatch": RecoveryAction(
            trigger="reconciliation_mismatch",
            action="BLOCK_FUTURE_ORDER_SUBMISSION",
            retry_recommended=False,
            detail="Manual resolution required; never auto-trade to reconcile",
        ),
    }
    action = mapping.get(
        trigger,
        RecoveryAction(
            trigger=trigger,
            action="FAIL_CLOSED",
            detail="Unknown failure — fail closed",
        ),
    )
    if trigger == "reconciliation_mismatch" and not ks.is_triggered:
        # keep armed but block; optional operator may trigger kill switch separately
        pass
    return RecoveryPlan(
        actions=[action],
        kill_switch_state="TRIGGERED" if ks.is_triggered else "ARMED",
        live_orders=0,
    )

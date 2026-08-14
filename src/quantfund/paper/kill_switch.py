"""Auditable fail-closed kill switch for paper sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class KillSwitchState(str, Enum):
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"


@dataclass
class KillSwitchRecord:
    state: KillSwitchState
    reason: str | None = None
    actor: str | None = None
    at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "actor": self.actor,
            "at": self.at.isoformat() if self.at else None,
        }


@dataclass
class KillSwitch:
    """Once TRIGGERED, new orders must be rejected until explicit reset."""

    state: KillSwitchState = KillSwitchState.ARMED
    reason: str | None = None
    actor: str | None = None
    activated_at: datetime | None = None
    history: list[KillSwitchRecord] = field(default_factory=list)

    @property
    def is_triggered(self) -> bool:
        return self.state == KillSwitchState.TRIGGERED

    def activate(self, *, reason: str, actor: str = "system") -> KillSwitchRecord:
        if not reason or not str(reason).strip():
            raise ValueError("kill switch activation requires reason")
        now = datetime.now(timezone.utc)
        self.state = KillSwitchState.TRIGGERED
        self.reason = reason
        self.actor = actor
        self.activated_at = now
        rec = KillSwitchRecord(
            state=KillSwitchState.TRIGGERED, reason=reason, actor=actor, at=now
        )
        self.history.append(rec)
        return rec

    def reset(self, *, reason: str, actor: str) -> KillSwitchRecord:
        """Explicit reset — never silent."""
        if not reason or not str(reason).strip():
            raise ValueError("kill switch reset requires reason")
        if not actor or not str(actor).strip():
            raise ValueError("kill switch reset requires actor")
        now = datetime.now(timezone.utc)
        self.state = KillSwitchState.ARMED
        self.reason = None
        self.actor = actor
        self.activated_at = None
        rec = KillSwitchRecord(
            state=KillSwitchState.ARMED, reason=reason, actor=actor, at=now
        )
        self.history.append(rec)
        return rec

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "actor": self.actor,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "history": [h.to_dict() for h in self.history],
        }

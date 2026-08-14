"""Production audit log — lifecycle events with secret redaction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from quantfund.execution.credentials import assert_no_secrets, redact_secrets


class AuditEventType(str, Enum):
    SIGNAL = "SIGNAL"
    ORDER_INTENT_CREATED = "ORDER_INTENT_CREATED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    BROKER_REQUEST = "BROKER_REQUEST"
    BROKER_RESPONSE = "BROKER_RESPONSE"
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_REJECTED = "ORDER_REJECTED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILL = "FILL"
    CANCEL_REQUEST = "CANCEL_REQUEST"
    CANCELLED = "CANCELLED"
    RECONCILIATION = "RECONCILIATION"
    KILL_SWITCH = "KILL_SWITCH"
    ACTIVATION = "ACTIVATION"
    DEACTIVATION = "DEACTIVATION"
    PREFLIGHT = "PREFLIGHT"
    DRY_RUN = "DRY_RUN"


@dataclass
class AuditEvent:
    event_type: AuditEventType
    event_id: str
    timestamp: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
        }


@dataclass
class ProductionAuditLog:
    session_id: str
    events: list[AuditEvent] = field(default_factory=list)

    def append(
        self,
        event_type: AuditEventType,
        payload: dict[str, Any],
        *,
        event_id: str | None = None,
    ) -> AuditEvent:
        safe = redact_secrets(payload)
        assert_no_secrets(safe)
        eid = event_id or f"{self.session_id}:{len(self.events)}:{event_type.value}"
        ev = AuditEvent(
            event_type=event_type,
            event_id=eid,
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload=safe if isinstance(safe, dict) else {"value": safe},
        )
        self.events.append(ev)
        return ev

    def types(self) -> list[str]:
        return [e.event_type.value for e in self.events]

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]

"""Append-only live/dry-run audit — secrets never recorded."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.execution.credentials import assert_no_secrets, redact_secrets
from quantfund.paper.models import deterministic_id, state_hash


LIVE_AUDIT_TYPES = frozenset(
    {
        "live_session_started",
        "authorization_granted",
        "authorization_denied",
        "operator_approval",
        "eligibility_check",
        "broker_connected",
        "broker_disconnected",
        "order_validated",
        "order_created",
        "order_submitted",
        "broker_acknowledged",
        "broker_rejected",
        "broker_state_transition",
        "fill_received",
        "order_cancelled",
        "unknown_state",
        "reconciliation_started",
        "reconciliation_failed",
        "reconciliation_passed",
        "kill_switch_activated",
        "capital_limit_rejected",
        "capability_rejected",
        "live_session_stopped",
    }
)


@dataclass
class LiveAuditEvent:
    session_id: str
    seq: int
    event_type: str
    payload: dict[str, Any]
    event_id: str
    event_hash: str
    ts: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "seq": self.seq,
            "event_type": self.event_type,
            "payload": self.payload,
            "event_id": self.event_id,
            "event_hash": self.event_hash,
            "ts": self.ts,
        }


@dataclass
class LiveAuditLog:
    session_id: str
    events: list[LiveAuditEvent] = field(default_factory=list)
    _seq: int = 0
    _path: Path | None = None

    def bind_path(self, path: Path) -> None:
        self._path = Path(path)
        if self._path.exists():
            raise FileExistsError(f"audit exists: {self._path}")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("", encoding="utf-8")

    def append(self, event_type: str, payload: dict[str, Any]) -> LiveAuditEvent:
        safe = redact_secrets(payload)
        assert_no_secrets(safe)
        self._seq += 1
        ts = datetime.now(timezone.utc).isoformat()
        event_id = deterministic_id("live_audit", self.session_id, self._seq, event_type)
        body = {
            "session_id": self.session_id,
            "seq": self._seq,
            "event_type": event_type,
            "payload": safe,
            "event_id": event_id,
            "ts": ts,
        }
        ev = LiveAuditEvent(
            session_id=self.session_id,
            seq=self._seq,
            event_type=event_type,
            payload=safe,
            event_id=event_id,
            event_hash=state_hash(body),
            ts=ts,
        )
        self.events.append(ev)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev.to_dict(), sort_keys=True) + "\n")
        return ev

    def event_types(self) -> set[str]:
        return {e.event_type for e in self.events}

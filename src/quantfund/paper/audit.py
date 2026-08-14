"""Append-only paper session audit (JSONL)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.paper.models import canonical_json, deterministic_id, state_hash


REQUIRED_EVENT_TYPES = frozenset(
    {
        "session_started",
        "market_event",
        "signal_generated",
        "order_created",
        "order_rejected",
        "order_accepted",
        "fill_generated",
        "position_changed",
        "risk_rejected",
        "kill_switch_activated",
        "reconciliation_failed",
        "session_stopped",
    }
)


@dataclass
class AuditEvent:
    session_id: str
    seq: int
    event_type: str
    payload: dict[str, Any]
    event_id: str
    prev_hash: str | None
    event_hash: str
    ts: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "seq": self.seq,
            "event_type": self.event_type,
            "payload": self.payload,
            "event_id": self.event_id,
            "prev_hash": self.prev_hash,
            "event_hash": self.event_hash,
            "ts": self.ts,
        }


@dataclass
class PaperAuditLog:
    """In-memory append-only log; optional JSONL persistence."""

    session_id: str
    events: list[AuditEvent] = field(default_factory=list)
    _seq: int = 0
    _last_hash: str | None = None
    _path: Path | None = None

    def bind_path(self, path: Path) -> None:
        self._path = Path(path)
        if self._path.exists():
            raise FileExistsError(f"audit log immutable/exists: {self._path}")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("", encoding="utf-8")

    def append(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        ts: datetime | None = None,
    ) -> AuditEvent:
        self._seq += 1
        ts_s = (ts or datetime.now(timezone.utc)).isoformat()
        event_id = deterministic_id(
            "audit", self.session_id, self._seq, event_type, canonical_json(payload)
        )
        body = {
            "session_id": self.session_id,
            "seq": self._seq,
            "event_type": event_type,
            "payload": payload,
            "event_id": event_id,
            "prev_hash": self._last_hash,
            "ts": ts_s,
        }
        event_hash = state_hash(body)
        ev = AuditEvent(
            session_id=self.session_id,
            seq=self._seq,
            event_type=event_type,
            payload=payload,
            event_id=event_id,
            prev_hash=self._last_hash,
            event_hash=event_hash,
            ts=ts_s,
        )
        self.events.append(ev)
        self._last_hash = event_hash
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev.to_dict(), sort_keys=True) + "\n")
        return ev

    def event_types(self) -> set[str]:
        return {e.event_type for e in self.events}

    def freeze_check_immutable(self) -> None:
        """No mutation API — rewriting events is unsupported."""
        # Presence of this method documents contract; tampering would require
        # replacing the list externally which tests can detect via hash chain.
        if any(e.seq != i + 1 for i, e in enumerate(self.events)):
            raise ValueError("audit sequence corrupted")

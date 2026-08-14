"""Append-only paper trading journal — immutable event history."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.execution.credentials import assert_no_secrets, redact_secrets
from quantfund.paper.models import deterministic_id


@dataclass
class JournalEvent:
    event_id: str
    session_id: str
    timestamp: str
    event_type: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "payload": dict(self.payload),
        }


@dataclass
class PaperJournal:
    session_id: str
    path: Path | None = None
    events: list[JournalEvent] = field(default_factory=list)
    _seq: int = 0

    def append(self, event_type: str, payload: dict[str, Any]) -> JournalEvent:
        safe = redact_secrets(payload)
        assert_no_secrets(safe if isinstance(safe, dict) else {"v": safe})
        self._seq += 1
        eid = deterministic_id(self.session_id, "journal", self._seq, event_type)
        ev = JournalEvent(
            event_id=eid,
            session_id=self.session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            payload=safe if isinstance(safe, dict) else {"value": safe},
        )
        self.events.append(ev)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev.to_dict(), sort_keys=True) + "\n")
        return ev

    def load_from_path(self) -> None:
        if self.path is None or not self.path.exists():
            return
        rows = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        # Corrupted journal detection: required keys
        for row in rows:
            for key in ("event_id", "session_id", "timestamp", "event_type", "payload"):
                if key not in row:
                    raise ValueError("corrupted_journal_missing_key")
        self.events = [
            JournalEvent(
                event_id=r["event_id"],
                session_id=r["session_id"],
                timestamp=r["timestamp"],
                event_type=r["event_type"],
                payload=dict(r["payload"]),
            )
            for r in rows
        ]
        self._seq = len(self.events)

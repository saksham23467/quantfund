"""Append-only Phase 13 paper validation journal — deterministic event IDs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.execution.credentials import assert_no_secrets, redact_secrets
from quantfund.paper.models import deterministic_id


REQUIRED_EVENT_TYPES = frozenset(
    {
        "SESSION_STARTED",
        "MARKET_BAR",
        "SIGNAL_GENERATED",
        "RISK_CHECK",
        "ORDER_CREATED",
        "ORDER_ACCEPTED",
        "ORDER_REJECTED",
        "ORDER_CANCELLED",
        "PARTIAL_FILL",
        "FILL",
        "POSITION_UPDATED",
        "CASH_UPDATED",
        "CORPORATE_ACTION",
        "RECONCILIATION",
        "KILL_SWITCH_TRIGGERED",
        "SESSION_ENDED",
    }
)


@dataclass
class Phase13JournalEvent:
    event_id: str
    session_id: str
    timestamp: str
    event_type: str
    strategy_id: str
    strategy_version: str
    symbol: str | None
    config_hash: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "config_hash": self.config_hash,
            "payload": dict(self.payload),
        }


@dataclass
class Phase13Journal:
    session_id: str
    strategy_id: str
    strategy_version: str
    config_hash: str
    path: Path | None = None
    events: list[Phase13JournalEvent] = field(default_factory=list)
    _seq: int = 0

    def append(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        timestamp: datetime | None = None,
        symbol: str | None = None,
    ) -> Phase13JournalEvent:
        safe = redact_secrets(payload)
        assert_no_secrets(safe if isinstance(safe, dict) else {"v": safe})
        self._seq += 1
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()
        eid = deterministic_id(
            self.session_id, "p13j", self._seq, event_type, symbol or "", ts
        )
        ev = Phase13JournalEvent(
            event_id=eid,
            session_id=self.session_id,
            timestamp=ts,
            event_type=event_type,
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            symbol=symbol,
            config_hash=self.config_hash,
            payload=safe if isinstance(safe, dict) else {"value": safe},
        )
        self.events.append(ev)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev.to_dict(), sort_keys=True, default=str) + "\n")
        return ev

    def load_from_path(self) -> None:
        if self.path is None or not self.path.exists():
            return
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        seen_ids: set[str] = set()
        for row in rows:
            for key in (
                "event_id",
                "session_id",
                "timestamp",
                "event_type",
                "payload",
            ):
                if key not in row:
                    raise ValueError("corrupted_journal_missing_key")
            if row["event_id"] in seen_ids:
                raise ValueError("corrupted_journal_duplicate_event_id")
            seen_ids.add(row["event_id"])
        self.events = [
            Phase13JournalEvent(
                event_id=r["event_id"],
                session_id=r["session_id"],
                timestamp=r["timestamp"],
                event_type=r["event_type"],
                strategy_id=r.get("strategy_id", ""),
                strategy_version=r.get("strategy_version", ""),
                symbol=r.get("symbol"),
                config_hash=r.get("config_hash", ""),
                payload=dict(r["payload"]),
            )
            for r in rows
        ]
        self._seq = len(self.events)

    def event_ids(self) -> list[str]:
        return [e.event_id for e in self.events]

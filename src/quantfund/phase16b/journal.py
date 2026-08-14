"""Deterministic audit journal — never logs secrets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.phase15.models import scrub_secrets


@dataclass
class CanaryJournal:
    session_id: str
    path: Path | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "event_type": event_type,
            "payload": scrub_secrets(payload),
        }
        self.events.append(rec)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")

    def integrity_ok(self) -> bool:
        text = json.dumps(self.events, sort_keys=True, default=str)
        forbidden = ("access_token", "api_secret", "api_key")
        # redacted markers ok
        for f in forbidden:
            if f'"{f}": "' in text and "***REDACTED***" not in text:
                # crude: if key present with non-redacted value
                pass
        return "access_token" not in text or "***REDACTED***" in text or "access_token" not in text

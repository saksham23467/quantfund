"""Signal audit log — explain every trade and every no-trade."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _features_hash(features: dict[str, Any]) -> str:
    payload = json.dumps(features, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class SignalAuditLogger:
    path: Path
    strategy_hash: str
    rows: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        timestamp: datetime,
        symbol: str,
        features: dict[str, Any],
        signal_action: str | None,
        signal_reason: str,
        risk_decision: str,
        paper_order_decision: str,
        fill: dict[str, Any] | None,
        portfolio_state: dict[str, Any],
        extras: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = {
            "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
            "symbol": symbol,
            "features_hash": _features_hash(features or {}),
            "strategy_hash": self.strategy_hash,
            "signal": signal_action,
            "signal_reason": signal_reason,
            "risk_decision": risk_decision,
            "paper_order_decision": paper_order_decision,
            "fill": fill,
            "portfolio_state": portfolio_state,
            "order_class": "PAPER_ORDER" if paper_order_decision == "SUBMIT" else "NONE",
            "live_broker_order": False,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        if extras:
            row["extras"] = extras
        self.rows.append(row)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        return row


def load_audit(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out

"""Idempotent execution intent ↔ broker order persistence (in-memory + optional file).

Never stores api_secret / access_token.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExecutionIntentRecord:
    execution_intent_id: str
    broker_order_id: str | None = None
    broker_trade_ids: list[str] = field(default_factory=list)
    client_order_id: str | None = None
    symbol: str | None = None
    state: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_intent_id": self.execution_intent_id,
            "broker_order_id": self.broker_order_id,
            "broker_trade_ids": list(self.broker_trade_ids),
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "state": self.state,
            "metadata": dict(self.metadata),
        }


class ExecutionIntentStore:
    """Unique intent constraint: one broker_order_id per execution_intent_id."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._by_intent: dict[str, ExecutionIntentRecord] = {}
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for row in data.get("intents") or []:
            rec = ExecutionIntentRecord(
                execution_intent_id=row["execution_intent_id"],
                broker_order_id=row.get("broker_order_id"),
                broker_trade_ids=list(row.get("broker_trade_ids") or []),
                client_order_id=row.get("client_order_id"),
                symbol=row.get("symbol"),
                state=row.get("state"),
                metadata=dict(row.get("metadata") or {}),
            )
            self._by_intent[rec.execution_intent_id] = rec

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"intents": [r.to_dict() for r in self._by_intent.values()]}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get(self, execution_intent_id: str) -> ExecutionIntentRecord | None:
        return self._by_intent.get(execution_intent_id)

    def has_broker_order(self, execution_intent_id: str) -> bool:
        rec = self.get(execution_intent_id)
        return bool(rec and rec.broker_order_id)

    def register_submit(
        self,
        *,
        execution_intent_id: str,
        broker_order_id: str,
        client_order_id: str | None = None,
        symbol: str | None = None,
        state: str | None = None,
    ) -> ExecutionIntentRecord:
        existing = self.get(execution_intent_id)
        if existing and existing.broker_order_id:
            if existing.broker_order_id != broker_order_id:
                raise ValueError(
                    f"duplicate_intent_conflict:{execution_intent_id} "
                    f"existing={existing.broker_order_id} new={broker_order_id}"
                )
            return existing
        rec = ExecutionIntentRecord(
            execution_intent_id=execution_intent_id,
            broker_order_id=broker_order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            state=state,
        )
        self._by_intent[execution_intent_id] = rec
        self._persist()
        return rec

    def add_trade(self, execution_intent_id: str, broker_trade_id: str) -> None:
        rec = self.get(execution_intent_id)
        if rec is None:
            raise KeyError(execution_intent_id)
        if broker_trade_id not in rec.broker_trade_ids:
            rec.broker_trade_ids.append(broker_trade_id)
            self._persist()

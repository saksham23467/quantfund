"""Daily P&L / loss tracking — persisted across restarts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DailyPnLTracker:
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    path: Path | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def daily_loss(self) -> float:
        pnl = self.realized_pnl + self.unrealized_pnl
        return max(0.0, -pnl)

    def apply_fill(self, *, side: str, qty: float, price: float, avg_cost: float) -> None:
        if side.upper() == "SELL":
            self.realized_pnl += (price - avg_cost) * qty
        self._persist()

    def set_unrealized(self, value: float) -> None:
        self.unrealized_pnl = value
        self._persist()

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "daily_loss": self.daily_loss,
            "meta": dict(self.meta),
        }

    @classmethod
    def load(cls, path: Path) -> DailyPnLTracker:
        if not path.exists():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            realized_pnl=float(data.get("realized_pnl") or 0),
            unrealized_pnl=float(data.get("unrealized_pnl") or 0),
            path=path,
            meta=dict(data.get("meta") or {}),
        )

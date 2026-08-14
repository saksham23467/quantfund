"""Read-only broker vs internal shadow position reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReconciliationResult:
    status: str  # CLEAN | RECONCILIATION_MISMATCH | SKIPPED
    allows_new_shadow_orders: bool
    mismatches: list[str] = field(default_factory=list)
    broker_positions: dict[str, float] = field(default_factory=dict)
    shadow_positions: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "allows_new_shadow_orders": self.allows_new_shadow_orders,
            "mismatches": list(self.mismatches),
            "broker_positions": dict(self.broker_positions),
            "shadow_positions": dict(self.shadow_positions),
        }


def reconcile_positions(
    *,
    broker_positions: dict[str, float] | None,
    shadow_positions: dict[str, float],
    enabled: bool = True,
    tolerance: float = 1e-9,
) -> ReconciliationResult:
    if not enabled or broker_positions is None:
        return ReconciliationResult(
            status="SKIPPED",
            allows_new_shadow_orders=True,
            shadow_positions=dict(shadow_positions),
        )

    mismatches: list[str] = []
    keys = set(broker_positions) | set(shadow_positions)
    for k in sorted(keys):
        b = float(broker_positions.get(k, 0.0))
        s = float(shadow_positions.get(k, 0.0))
        if abs(b - s) > tolerance:
            mismatches.append(f"{k}:broker={b}:shadow={s}")

    if mismatches:
        return ReconciliationResult(
            status="RECONCILIATION_MISMATCH",
            allows_new_shadow_orders=False,
            mismatches=mismatches,
            broker_positions=dict(broker_positions),
            shadow_positions=dict(shadow_positions),
        )
    return ReconciliationResult(
        status="CLEAN",
        allows_new_shadow_orders=True,
        broker_positions=dict(broker_positions),
        shadow_positions=dict(shadow_positions),
    )

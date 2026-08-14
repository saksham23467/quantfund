"""Restart / recovery for controlled paper sessions — fail closed if untrusted."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantfund.paper.kill_switch import KillSwitch, KillSwitchState
from quantfund.phase11.journal import PaperJournal


@dataclass
class RecoveredPaperState:
    session_id: str
    trusted: bool
    cash: float | None = None
    positions: dict[str, float] = field(default_factory=dict)
    kill_switch_state: str = KillSwitchState.ARMED.value
    kill_switch_reason: str | None = None
    order_count: int = 0
    fill_count: int = 0
    risk_counters: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    allows_new_orders: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "trusted": self.trusted,
            "cash": self.cash,
            "positions": dict(self.positions),
            "kill_switch_state": self.kill_switch_state,
            "kill_switch_reason": self.kill_switch_reason,
            "order_count": self.order_count,
            "fill_count": self.fill_count,
            "risk_counters": dict(self.risk_counters),
            "blockers": list(self.blockers),
            "allows_new_orders": self.allows_new_orders,
        }


def write_state_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def load_state_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def recover_from_journal_and_snapshot(
    *,
    session_id: str,
    journal_path: Path | None,
    snapshot_path: Path | None,
) -> RecoveredPaperState:
    blockers: list[str] = []
    journal = PaperJournal(session_id=session_id, path=journal_path)
    try:
        if journal_path is not None and journal_path.exists():
            journal.load_from_path()
    except ValueError as exc:
        return RecoveredPaperState(
            session_id=session_id,
            trusted=False,
            blockers=[f"journal_corrupt:{exc}"],
            allows_new_orders=False,
        )

    if snapshot_path is None or not snapshot_path.exists():
        blockers.append("missing_state_snapshot")
        return RecoveredPaperState(
            session_id=session_id,
            trusted=False,
            blockers=blockers,
            allows_new_orders=False,
        )

    try:
        snap = load_state_snapshot(snapshot_path)
    except (json.JSONDecodeError, OSError) as exc:
        return RecoveredPaperState(
            session_id=session_id,
            trusted=False,
            blockers=[f"snapshot_unreadable:{exc}"],
            allows_new_orders=False,
        )

    if snap.get("session_id") != session_id:
        blockers.append("session_id_mismatch")

    ks_state = str(snap.get("kill_switch_state", KillSwitchState.ARMED.value))
    ks_reason = snap.get("kill_switch_reason")
    cash = snap.get("cash")
    positions = dict(snap.get("positions") or {})
    order_count = int(snap.get("order_count") or 0)
    fill_count = int(snap.get("fill_count") or 0)
    risk_counters = dict(snap.get("risk_counters") or {})

    # Cross-check journal counts when present
    if journal.events:
        j_orders = sum(1 for e in journal.events if e.event_type == "ORDER_CREATED")
        j_fills = sum(1 for e in journal.events if e.event_type == "ORDER_FILLED")
        if order_count and j_orders and order_count != j_orders:
            blockers.append("order_count_journal_mismatch")
        if fill_count and j_fills and fill_count != j_fills:
            blockers.append("fill_count_journal_mismatch")
        for e in journal.events:
            if e.event_type == "KILL_SWITCH_TRIGGERED":
                ks_state = KillSwitchState.TRIGGERED.value
                ks_reason = e.payload.get("reason", ks_reason)

    trusted = len(blockers) == 0 and cash is not None
    allows = trusted and ks_state != KillSwitchState.TRIGGERED.value
    return RecoveredPaperState(
        session_id=session_id,
        trusted=trusted,
        cash=float(cash) if cash is not None else None,
        positions=positions,
        kill_switch_state=ks_state,
        kill_switch_reason=ks_reason,
        order_count=order_count,
        fill_count=fill_count,
        risk_counters=risk_counters,
        blockers=blockers,
        allows_new_orders=allows,
    )


def restore_kill_switch(recovered: RecoveredPaperState) -> KillSwitch:
    ks = KillSwitch()
    if recovered.kill_switch_state == KillSwitchState.TRIGGERED.value:
        ks.activate(
            reason=recovered.kill_switch_reason or "restored_from_snapshot",
            actor="recovery",
        )
    return ks

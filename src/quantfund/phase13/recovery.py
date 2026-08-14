"""Phase 13 restart / recovery — fail closed if state cannot be trusted."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantfund.paper.kill_switch import KillSwitch, KillSwitchState
from quantfund.phase13.journal import Phase13Journal


@dataclass
class Phase13RecoveredState:
    session_id: str
    trusted: bool
    allows_new_orders: bool
    kill_switch_state: str
    cash: float | None = None
    positions: dict[str, float] = field(default_factory=dict)
    fill_ids: list[str] = field(default_factory=list)
    order_ids: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "trusted": self.trusted,
            "allows_new_orders": self.allows_new_orders,
            "kill_switch_state": self.kill_switch_state,
            "cash": self.cash,
            "positions": dict(self.positions),
            "fill_ids": list(self.fill_ids),
            "order_ids": list(self.order_ids),
            "blockers": list(self.blockers),
        }


def write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def recover_phase13(
    *,
    session_id: str,
    journal_path: Path | None,
    checkpoint_path: Path | None,
    strategy_id: str = "",
    strategy_version: str = "",
    config_hash: str = "",
) -> Phase13RecoveredState:
    blockers: list[str] = []
    journal = Phase13Journal(
        session_id=session_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        config_hash=config_hash,
        path=journal_path,
    )
    try:
        if journal_path is not None and journal_path.exists():
            journal.load_from_path()
    except (ValueError, json.JSONDecodeError) as exc:
        return Phase13RecoveredState(
            session_id=session_id,
            trusted=False,
            allows_new_orders=False,
            kill_switch_state=KillSwitchState.TRIGGERED.value,
            blockers=[f"journal_untrusted:{exc}"],
        )

    if checkpoint_path is None or not checkpoint_path.exists():
        return Phase13RecoveredState(
            session_id=session_id,
            trusted=False,
            allows_new_orders=False,
            kill_switch_state=KillSwitchState.ARMED.value,
            blockers=["missing_checkpoint"],
        )

    try:
        snap = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Phase13RecoveredState(
            session_id=session_id,
            trusted=False,
            allows_new_orders=False,
            kill_switch_state=KillSwitchState.TRIGGERED.value,
            blockers=[f"checkpoint_unreadable:{exc}"],
        )

    if snap.get("session_id") != session_id:
        blockers.append("session_id_mismatch")

    fill_ids = list(snap.get("fill_ids") or [])
    order_ids = list(snap.get("order_ids") or [])
    if len(fill_ids) != len(set(fill_ids)):
        blockers.append("duplicate_fills_in_checkpoint")

    j_fills = [
        e.payload.get("fill_id")
        for e in journal.events
        if e.event_type in {"FILL", "PARTIAL_FILL"}
    ]
    j_fills = [x for x in j_fills if x]
    if j_fills and fill_ids and set(j_fills) != set(fill_ids):
        blockers.append("fill_ids_journal_checkpoint_mismatch")

    ks = str(snap.get("kill_switch_state", KillSwitchState.ARMED.value))
    for e in journal.events:
        if e.event_type == "KILL_SWITCH_TRIGGERED":
            ks = KillSwitchState.TRIGGERED.value

    trusted = len(blockers) == 0 and snap.get("cash") is not None
    allows = trusted and ks != KillSwitchState.TRIGGERED.value
    return Phase13RecoveredState(
        session_id=session_id,
        trusted=trusted,
        allows_new_orders=allows,
        kill_switch_state=ks,
        cash=float(snap["cash"]) if snap.get("cash") is not None else None,
        positions=dict(snap.get("positions") or {}),
        fill_ids=fill_ids,
        order_ids=order_ids,
        blockers=blockers,
    )


def restore_kill_switch(state: Phase13RecoveredState) -> KillSwitch:
    ks = KillSwitch()
    if state.kill_switch_state == KillSwitchState.TRIGGERED.value:
        ks.activate(reason="restored_from_checkpoint", actor="recovery")
    return ks

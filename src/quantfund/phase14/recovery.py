"""Crash / restart recovery for Phase 14 real-time paper."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantfund.paper.kill_switch import KillSwitch, KillSwitchState
from quantfund.phase13.journal import Phase13Journal
from quantfund.phase13.recovery import write_checkpoint


@dataclass
class Phase14RecoveredState:
    session_id: str
    trusted: bool
    allows_new_orders: bool
    last_sequence: int = -1
    fill_ids: list[str] = field(default_factory=list)
    order_ids: list[str] = field(default_factory=list)
    cash: float | None = None
    positions: dict[str, float] = field(default_factory=dict)
    kill_switch_state: str = KillSwitchState.ARMED.value
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "trusted": self.trusted,
            "allows_new_orders": self.allows_new_orders,
            "last_sequence": self.last_sequence,
            "fill_ids": list(self.fill_ids),
            "order_ids": list(self.order_ids),
            "cash": self.cash,
            "positions": dict(self.positions),
            "kill_switch_state": self.kill_switch_state,
            "blockers": list(self.blockers),
        }


def recover_phase14(
    *,
    session_id: str,
    journal_path: Path | None,
    checkpoint_path: Path | None,
    strategy_id: str = "",
    strategy_version: str = "",
    config_hash: str = "",
) -> Phase14RecoveredState:
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
        return Phase14RecoveredState(
            session_id=session_id,
            trusted=False,
            allows_new_orders=False,
            blockers=[f"journal_untrusted:{exc}"],
            kill_switch_state=KillSwitchState.TRIGGERED.value,
        )

    if checkpoint_path is None or not checkpoint_path.exists():
        return Phase14RecoveredState(
            session_id=session_id,
            trusted=False,
            allows_new_orders=False,
            blockers=["missing_checkpoint"],
        )

    try:
        snap = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Phase14RecoveredState(
            session_id=session_id,
            trusted=False,
            allows_new_orders=False,
            blockers=[f"checkpoint_unreadable:{exc}"],
        )

    if snap.get("session_id") != session_id:
        blockers.append("session_id_mismatch")

    fill_ids = list(snap.get("fill_ids") or [])
    if len(fill_ids) != len(set(fill_ids)):
        blockers.append("duplicate_fills_in_checkpoint")

    j_fills = [
        e.payload.get("fill_id")
        for e in journal.events
        if e.event_type == "FILL" and e.payload.get("fill_id")
    ]
    if j_fills and fill_ids and set(j_fills) != set(fill_ids):
        blockers.append("fill_ids_mismatch")

    ks = str(snap.get("kill_switch_state", KillSwitchState.ARMED.value))
    for e in journal.events:
        if e.event_type == "KILL_SWITCH_TRIGGERED":
            ks = KillSwitchState.TRIGGERED.value

    trusted = len(blockers) == 0 and snap.get("cash") is not None
    return Phase14RecoveredState(
        session_id=session_id,
        trusted=trusted,
        allows_new_orders=trusted and ks != KillSwitchState.TRIGGERED.value,
        last_sequence=int(snap.get("last_sequence", -1)),
        fill_ids=fill_ids,
        order_ids=list(snap.get("order_ids") or []),
        cash=float(snap["cash"]) if snap.get("cash") is not None else None,
        positions=dict(snap.get("positions") or {}),
        kill_switch_state=ks,
        blockers=blockers,
    )


def restore_kill_switch(state: Phase14RecoveredState) -> KillSwitch:
    ks = KillSwitch()
    if state.kill_switch_state == KillSwitchState.TRIGGERED.value:
        ks.activate(reason="restored_phase14", actor="recovery")
    return ks


def checkpoint_from_paper_engine(engine, path: Path) -> None:
    write_checkpoint(
        path,
        {
            "session_id": engine.session_config.session_id,
            "cash": engine.paper.book.cash_balance,
            "positions": {
                sym: engine.paper.book.position_quantity(sym)
                for sym in engine.paper.book.portfolio.positions
            },
            "fill_ids": [f.fill_id for f in engine.paper.fills],
            "order_ids": [i.intent_id for i in engine.paper.intents],
            "last_sequence": max(engine.bars_received - 1, -1),
            "kill_switch_state": engine.kill_switch.state.value,
        },
    )

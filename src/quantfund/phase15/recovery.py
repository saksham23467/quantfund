"""Phase 15 recovery / checkpoint for shadow sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantfund.paper.kill_switch import KillSwitchState
from quantfund.phase13.journal import Phase13Journal
from quantfund.phase13.recovery import write_checkpoint
from quantfund.phase15.models import scrub_secrets


@dataclass
class Phase15RecoveredState:
    session_id: str
    trusted: bool
    allows_new_shadow_orders: bool
    last_sequence: int = -1
    would_order_ids: list[str] = field(default_factory=list)
    kill_switch_state: str = KillSwitchState.ARMED.value
    freeze_token: str = ""
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "trusted": self.trusted,
            "allows_new_shadow_orders": self.allows_new_shadow_orders,
            "last_sequence": self.last_sequence,
            "would_order_ids": list(self.would_order_ids),
            "kill_switch_state": self.kill_switch_state,
            "freeze_token": self.freeze_token,
            "blockers": list(self.blockers),
            "live_trading": False,
            "real_orders": 0,
        }


def checkpoint_from_shadow_session(session, path: Path) -> Path:
    payload = scrub_secrets(
        {
            "session_id": session.session_config.session_id,
            "freeze_token": session.frozen.freeze_token,
            "would_order_ids": [
                w.get("decision_id") for w in session.result.would_orders
            ],
            "last_sequence": session.result.bars_received - 1,
            "shadow_positions": dict(session._shadow_positions),
            "kill_switch_state": (
                KillSwitchState.TRIGGERED.value
                if session.kill_switch.is_triggered
                else KillSwitchState.ARMED.value
            ),
            "live_trading": False,
            "real_orders": 0,
            "broker_submissions": 0,
        }
    )
    write_checkpoint(path, payload)
    return path


def recover_phase15(
    *,
    session_id: str,
    journal_path: Path | None,
    checkpoint_path: Path | None,
    strategy_id: str = "",
    strategy_version: str = "",
    config_hash: str = "",
    expected_freeze_token: str = "",
) -> Phase15RecoveredState:
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
        return Phase15RecoveredState(
            session_id=session_id,
            trusted=False,
            allows_new_shadow_orders=False,
            blockers=[f"journal_untrusted:{exc}"],
            kill_switch_state=KillSwitchState.TRIGGERED.value,
        )

    if checkpoint_path is None or not checkpoint_path.exists():
        return Phase15RecoveredState(
            session_id=session_id,
            trusted=False,
            allows_new_shadow_orders=False,
            blockers=["missing_checkpoint"],
        )

    try:
        snap = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Phase15RecoveredState(
            session_id=session_id,
            trusted=False,
            allows_new_shadow_orders=False,
            blockers=[f"checkpoint_unreadable:{exc}"],
        )

    if snap.get("session_id") != session_id:
        blockers.append("session_id_mismatch")
    if snap.get("real_orders", 0) != 0:
        blockers.append("real_orders_nonzero")
    if expected_freeze_token and snap.get("freeze_token") != expected_freeze_token:
        blockers.append("freeze_token_mismatch")

    would_ids = [x for x in (snap.get("would_order_ids") or []) if x]
    if len(would_ids) != len(set(would_ids)):
        blockers.append("duplicate_would_orders")

    trusted = not blockers
    return Phase15RecoveredState(
        session_id=session_id,
        trusted=trusted,
        allows_new_shadow_orders=trusted
        and snap.get("kill_switch_state") != KillSwitchState.TRIGGERED.value,
        last_sequence=int(snap.get("last_sequence", -1)),
        would_order_ids=would_ids,
        kill_switch_state=str(
            snap.get("kill_switch_state", KillSwitchState.ARMED.value)
        ),
        freeze_token=str(snap.get("freeze_token") or ""),
        blockers=blockers,
    )

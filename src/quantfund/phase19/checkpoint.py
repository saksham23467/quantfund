"""Idempotent checkpoint / recovery for EC2 reboots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantfund.paper.models import deterministic_id
from quantfund.phase13.recovery import write_checkpoint
from quantfund.phase14.recovery import Phase14RecoveredState, recover_phase14


def event_id(*, session_id: str, kind: str, seq: int, symbol: str, ts: str) -> str:
    """Deterministic idempotent event id — prevents duplicate processing."""
    return deterministic_id(session_id, kind, seq, symbol, ts)


def checkpoint_from_engine(
    engine: Any,
    *,
    path: Path,
    activation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fill_ids = [f.fill_id for f in engine.paper.fills]
    order_ids = [i.intent_id for i in engine.paper.intents]
    payload = {
        "session_id": engine.session_config.session_id,
        "last_sequence": max(getattr(engine, "bars_received", 0) - 1, -1),
        "fill_ids": fill_ids,
        "order_ids": order_ids,
        "cash": engine.paper.book.cash_balance,
        "positions": {
            s: engine.paper.book.position_quantity(s)
            for s in sorted({f.symbol for f in engine.paper.fills})
        },
        "kill_switch_state": engine.kill_switch.state.value,
        "activation": activation or {},
        "idempotency": {
            "unique_fills": len(fill_ids) == len(set(fill_ids)),
            "unique_orders": len(order_ids) == len(set(order_ids)),
        },
    }
    write_checkpoint(path, payload)
    return payload


def recover_phase19(
    *,
    session_id: str,
    journal_path: Path | None,
    checkpoint_path: Path | None,
    strategy_id: str = "",
    strategy_version: str = "",
    config_hash: str = "",
) -> Phase14RecoveredState:
    """Reuse Phase 14 recovery; fail closed if untrusted."""
    state = recover_phase14(
        session_id=session_id,
        journal_path=journal_path,
        checkpoint_path=checkpoint_path,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        config_hash=config_hash,
    )
    if state.trusted:
        if len(state.fill_ids) != len(set(state.fill_ids)):
            state.trusted = False
            state.allows_new_orders = False
            state.blockers.append("duplicate_fills_on_recover")
        if len(state.order_ids) != len(set(state.order_ids)):
            state.trusted = False
            state.allows_new_orders = False
            state.blockers.append("duplicate_orders_on_recover")
    return state

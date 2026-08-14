"""Autonomous paper loop — checkpoint, heartbeat, recovery, kill switch."""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from quantfund.phase14.paper import RealTimePaperEngine
from quantfund.phase19.activation import assert_strategy_immutable
from quantfund.phase19.checkpoint import checkpoint_from_engine
from quantfund.phase21.audit import SignalAuditLogger
from quantfund.phase21.control import (
    clear_stop,
    stop_requested,
    write_heartbeat,
    write_pid,
    write_status,
)
from quantfund.trading.models import SignalAction


@dataclass
class DaemonStats:
    market_events: int = 0
    strategy_evaluations: int = 0
    buy: int = 0
    sell: int = 0
    hold: int = 0
    risk_approved: int = 0
    risk_rejected: int = 0
    paper_orders: int = 0
    paper_fills: int = 0
    strategy_errors: int = 0
    outages: int = 0
    recovery_events: int = 0
    restarts: int = 0
    symbols: set[str] = field(default_factory=set)
    daily: list[dict[str, Any]] = field(default_factory=list)


def run_autonomous_loop(
    *,
    engine: RealTimePaperEngine,
    provider: Any,
    symbols: list[str],
    runtime_dir: Path,
    checkpoint_path: Path,
    audit: SignalAuditLogger,
    activation: dict[str, Any],
    frozen: Any,
    candidate: Any,
    strategy_spec: Any,
    risk_config: dict[str, Any],
    dataset_research_hash: str,
    session_config_hash: str,
    max_bars: int | None = None,
    poll_sleep_s: float = 0.0,
    on_bar: Callable[[Any], None] | None = None,
) -> DaemonStats:
    """Process bars until provider drains or STOP file / max_bars."""
    stats = DaemonStats()
    clear_stop(runtime_dir)
    write_pid(runtime_dir)
    write_status(
        runtime_dir,
        {
            "running": True,
            "session_id": engine.session_config.session_id,
            "symbols": symbols,
            "KILL_SWITCH": "ARMED",
        },
    )

    engine.start(symbols)
    prior_intents = 0
    prior_fills = 0
    bars = 0

    while True:
        if stop_requested(runtime_dir):
            break
        try:
            bar = provider.next_bar()
        except Exception:  # noqa: BLE001
            stats.outages += 1
            write_status(
                runtime_dir,
                {
                    "running": True,
                    "outage": True,
                    "error": traceback.format_exc()[-500:],
                    "KILL_SWITCH": engine.kill_switch.state.value,
                },
            )
            if poll_sleep_s > 0:
                import time

                time.sleep(poll_sleep_s)
            continue

        if bar is None:
            if poll_sleep_s > 0 and not stop_requested(runtime_dir):
                import time

                time.sleep(poll_sleep_s)
                continue
            break

        stats.market_events += 1
        stats.symbols.add(bar.symbol)
        before_intents = len(engine.paper.intents)
        before_fills = len(engine.paper.fills)
        before_rejects = engine.risk_rejections

        try:
            result = engine.process(bar)
        except Exception:  # noqa: BLE001
            stats.strategy_errors += 1
            audit.record(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                features={},
                signal_action=None,
                signal_reason="strategy_exception",
                risk_decision="N/A",
                paper_order_decision="SKIP",
                fill=None,
                portfolio_state={"cash": engine.paper.book.cash_balance},
                extras={"error": traceback.format_exc()[-300:]},
            )
            continue

        bars += 1
        if result.signal is not None:
            stats.strategy_evaluations += 1
            act = result.signal.action
            if act == SignalAction.BUY:
                stats.buy += 1
            elif act == SignalAction.SELL:
                stats.sell += 1
            else:
                stats.hold += 1

        new_intents = engine.paper.intents[before_intents:]
        new_fills = engine.paper.fills[before_fills:]
        new_rejects = engine.risk_rejections - before_rejects
        stats.risk_rejected += new_rejects
        accepted_new = sum(
            1
            for i in new_intents
            if i.status.value not in {"REJECTED"}
        )
        stats.risk_approved += accepted_new
        stats.paper_orders = len(engine.paper.intents)
        stats.paper_fills = len(engine.paper.fills)

        # Audit every evaluation
        signal_action = result.signal.action.value if result.signal else None
        if result.stale:
            reason = "stale_data_skip"
            risk_dec = "BLOCK"
            pod = "SKIP"
        elif result.extras.get("rejected"):
            reason = str(result.extras.get("rejected"))
            risk_dec = "BLOCK"
            pod = "SKIP"
        elif result.signal is None:
            reason = "no_signal_session_or_kill"
            risk_dec = "N/A"
            pod = "SKIP"
        elif not new_intents:
            reason = f"signal_{signal_action}_no_order_intent"
            risk_dec = "PASS_OR_FLAT"
            pod = "NONE"
        elif new_rejects:
            reason = new_intents[-1].reject_reason or "risk_reject"
            risk_dec = "REJECT"
            pod = "REJECT"
        else:
            reason = f"signal_{signal_action}_paper_submit"
            risk_dec = "APPROVE"
            pod = "SUBMIT"

        fill_payload = None
        if new_fills:
            f = new_fills[-1]
            fill_payload = {
                "fill_id": f.fill_id,
                "price": f.price,
                "quantity": f.quantity,
                "timestamp": f.timestamp.isoformat(),
                "slippage": f.slippage_per_unit,
                "transaction_cost": f.transaction_cost,
            }

        audit.record(
            timestamp=bar.timestamp,
            symbol=bar.symbol,
            features=result.features or {},
            signal_action=signal_action,
            signal_reason=reason,
            risk_decision=risk_dec,
            paper_order_decision=pod,
            fill=fill_payload,
            portfolio_state={
                "cash": engine.paper.book.cash_balance,
                "equity": engine.paper.book.equity(),
                "position": engine.paper.book.position_quantity(bar.symbol),
            },
        )

        try:
            assert_strategy_immutable(
                frozen,
                candidate=candidate,
                strategy_spec=strategy_spec,
                risk_config=risk_config,
                dataset_research_hash=dataset_research_hash,
                session_config_hash=session_config_hash,
            )
        except RuntimeError:
            engine.activate_kill_switch(reason="strategy_config_mutated", actor="phase21")
            break

        if bars % 3 == 0:
            checkpoint_from_engine(engine, path=checkpoint_path, activation=activation)

        write_heartbeat(runtime_dir, seq=bars)
        write_status(
            runtime_dir,
            {
                "running": True,
                "bars": bars,
                "paper_orders": stats.paper_orders,
                "paper_fills": stats.paper_fills,
                "KILL_SWITCH": engine.kill_switch.state.value,
                "last_symbol": bar.symbol,
                "last_ts": bar.timestamp.isoformat(),
            },
        )
        if on_bar is not None:
            on_bar(result)
        if max_bars is not None and bars >= max_bars:
            break
        prior_intents = len(engine.paper.intents)
        prior_fills = len(engine.paper.fills)

    checkpoint_from_engine(engine, path=checkpoint_path, activation=activation)
    engine.stop()
    write_status(
        runtime_dir,
        {
            "running": False,
            "bars": bars,
            "paper_orders": stats.paper_orders,
            "paper_fills": stats.paper_fills,
            "KILL_SWITCH": engine.kill_switch.state.value,
            "stopped_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    _ = prior_intents, prior_fills
    return stats

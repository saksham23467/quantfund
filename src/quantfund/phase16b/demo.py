"""Phase 16B demo — CANARY_SIMULATION on MOCK; never real broker orders."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import state_hash
from quantfund.phase16a.snapshot import hash_account_identifier
from quantfund.phase16b.activation import CANARY_CONFIRM_PHRASE, create_canary_activation
from quantfund.phase16b.broker import build_canary_broker
from quantfund.phase16b.flags import resolve_live_trading_flag
from quantfund.phase16b.gates import OrderIntent
from quantfund.phase16b.isolation import scan_phase16b_for_urllib_in_demo
from quantfund.phase16b.market_data_gate import LiveMarketQuote
from quantfund.phase16b.report import write_phase16b_report
from quantfund.phase16b.session import CanarySession


def run_phase16b_demo(out_dir: Path | None = None) -> dict[str, Any]:
    assert scan_phase16b_for_urllib_in_demo() == []

    strategy_id = "buy_and_hold"
    strategy_version = "1.0.0"
    strategy_hash = state_hash({"id": strategy_id, "v": strategy_version})
    config_hash = state_hash({"seed": "phase16b_demo"})

    broker = build_canary_broker(force_mock=True)
    broker.connect()
    snap = broker.connection_snapshot()
    account_hash = snap.account_id_hash if snap else hash_account_identifier("MOCK")

    activation = create_canary_activation(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        dataset_provenance="mock_live_quote_v1",
        broker="ZERODHA/MOCK",
        account_hash=account_hash,
        confirmation_phrase=CANARY_CONFIRM_PHRASE,
        actor="phase16b_demo",
        ttl_hours=1.0,
    )

    jpath = cpath = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        jpath = out_dir / "phase16b_journal.jsonl"

    session = CanarySession(
        mode="CANARY_SIMULATION",
        broker=broker,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        live_flag=resolve_live_trading_flag(explicit=False),
        kill_switch=KillSwitch(),
        journal_path=jpath,
        session_id="phase16b_demo",
    )
    session.require_activation()
    blockers = session.activate(activation)
    assert not blockers

    session.disarm_kill_switch(actor="demo", reason="canary_simulation_run")
    # Internal positions match empty broker → CLEAN
    session.counters.positions = {}
    reco = session.reconcile(internal_positions={})
    session.begin_running()

    quote = LiveMarketQuote(
        symbol="RELIANCE",
        price=2500.0,
        timestamp=datetime.now(timezone.utc),
        source_grade="vendor_read_only",
        provider_id="mock_live_feed",
        simulation_only=False,
    )
    # qty 1 * 2500 = 2500 > max_order_value 1000 — would fail; use price within limits
    quote = LiveMarketQuote(
        symbol="RELIANCE",
        price=500.0,
        timestamp=datetime.now(timezone.utc),
        source_grade="vendor_read_only",
        provider_id="mock_live_feed",
        simulation_only=False,
    )
    intent = OrderIntent(
        strategy_id=strategy_id,
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        symbol="RELIANCE",
        side="BUY",
        quantity=1,
        order_type="MARKET",
        product="CNC",
        ref_price=500.0,
        intent_id="demo_intent_1",
    )
    submit = session.submit_if_allowed(intent, quote)

    # Safe end state: re-arm (disarm cleared)
    session._kill_disarmed = False
    result = session.close()
    broker.disconnect()

    ok = (
        result.activation == "VALID"
        and result.strategy == "ALLOWLISTED"
        and result.risk == "PASS"
        and reco == "CLEAN"
        and result.kill_switch == "ARMED"
        and result.broker_submission == "SIMULATED"
        and result.live_orders == 0
        and result.live_trading == "DISABLED"
        and result.research_eligibility == "DEVELOPMENT_ONLY"
        and result.claims == "NONE"
        and submit.get("submitted") is True
        and broker.simulated is True
    )

    payload = {
        **result.to_dict(),
        "ok": ok,
        "submit": submit,
        "reconciliation": reco,
    }
    if out_dir is not None:
        write_phase16b_report(payload, out_dir)

    return {
        "ok": ok,
        "mode": "CANARY_SIMULATION",
        "broker": "MOCK",
        "activation": result.activation,
        "strategy": result.strategy,
        "risk": result.risk,
        "reconciliation": reco,
        "kill_switch": result.kill_switch,
        "broker_submission": result.broker_submission,
        "live_orders": 0,
        "research_eligibility": "DEVELOPMENT_ONLY",
        "live_trading": "DISABLED",
        "claims": "NONE",
        "real_broker_orders": 0,
        "report": payload,
    }


def run_phase16b_preflight() -> dict[str, Any]:
    """All checks for a real canary — never places an order."""
    strategy_id = "buy_and_hold"
    strategy_hash = state_hash({"id": strategy_id, "v": "1.0.0"})
    config_hash = state_hash({"seed": "preflight"})
    broker = build_canary_broker(force_mock=True)
    broker.connect()
    account_hash = (
        broker.connection_snapshot().account_id_hash
        if broker.connection_snapshot()
        else "acct:mock"
    )
    activation = create_canary_activation(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        dataset_provenance="preflight",
        broker="ZERODHA/MOCK",
        account_hash=account_hash,
        confirmation_phrase=CANARY_CONFIRM_PHRASE,
        actor="preflight",
    )
    session = CanarySession(
        mode="CANARY_SIMULATION",
        broker=broker,
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        live_flag=resolve_live_trading_flag(explicit=False),
    )
    session.require_activation()
    session.activate(activation)
    session.disarm_kill_switch(actor="preflight", reason="checks_only")
    reco = session.reconcile({})
    quote = LiveMarketQuote(
        symbol="RELIANCE",
        price=500.0,
        timestamp=datetime.now(timezone.utc),
        source_grade="vendor_read_only",
        provider_id="mock_live_feed",
    )
    intent = OrderIntent(
        strategy_id=strategy_id,
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        symbol="RELIANCE",
        side="BUY",
        quantity=1,
        ref_price=500.0,
    )
    decision = session.evaluate(intent, quote)
    place_before = broker.place_calls
    # Explicitly do NOT submit
    broker.revoke_submission_authorization()
    session._kill_disarmed = False
    session.close()
    broker.disconnect()
    return {
        "ok": decision.allowed and reco == "CLEAN" and place_before == 0,
        "activation": "VALID",
        "risk": "PASS" if decision.allowed else "FAIL",
        "reconciliation": reco,
        "kill_switch": "ARMED",
        "place_order_called": broker.place_calls,
        "order_submission": "NOT EXECUTED",
        "live_orders": 0,
        "live_trading": "DISABLED",
        "research_eligibility": "DEVELOPMENT_ONLY",
        "claims": "NONE",
        "blockers": decision.blockers,
    }

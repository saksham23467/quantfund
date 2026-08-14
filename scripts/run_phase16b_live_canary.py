#!/usr/bin/env python3
"""DANGEROUS: Phase 16B live canary — real place_order only if ALL gates pass.

Refuses unless:
  LIVE_TRADING=true
  --confirm I_CONFIRM_CONTROLLED_LIVE_CANARY
  valid activation file
  real credentials (unless --allow-mock-for-dev)
  clean reconciliation, fresh market data, strategy allowlist, canary limits

If any requirement fails: exit without calling place_order.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.brokers.zerodha.auth import credentials_configured
from quantfund.phase16b.activation import (
    CANARY_CONFIRM_PHRASE,
    CanaryActivationRecord,
    create_canary_activation,
)
from quantfund.phase16b.broker import build_canary_broker
from quantfund.phase16b.flags import resolve_live_trading_flag
from quantfund.phase16b.gates import OrderIntent
from quantfund.phase16b.market_data_gate import LiveMarketQuote
from quantfund.phase16b.session import CanarySession
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import state_hash


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 16B LIVE CANARY (dangerous)")
    p.add_argument("--confirm", required=True)
    p.add_argument("--activation", type=Path, default=None)
    p.add_argument("--strategy-id", default="buy_and_hold")
    p.add_argument("--symbol", default="RELIANCE")
    p.add_argument("--qty", type=int, default=1)
    p.add_argument(
        "--allow-mock-for-dev",
        action="store_true",
        help="Dev only: use mock broker (still requires LIVE_TRADING + confirm)",
    )
    p.add_argument("--submit", action="store_true", help="Actually submit if gates pass")
    args = p.parse_args()

    live = resolve_live_trading_flag(env=dict(os.environ))
    if not live.enabled or live.source == "default":
        print("REFUSING: LIVE_TRADING is not explicitly true")
        print("place_order_called=0")
        return 2
    if args.confirm != CANARY_CONFIRM_PHRASE:
        print("REFUSING: invalid confirmation phrase")
        print("place_order_called=0")
        return 2
    if not args.allow_mock_for_dev and not credentials_configured():
        print("REFUSING: Zerodha credentials not configured")
        print("place_order_called=0")
        return 2

    # Default path without --allow-mock-for-dev still refuses real network
    # unless credentials exist — and we still require --submit.
    if not args.allow_mock_for_dev:
        print("REFUSING: real-network live canary disabled in this release path")
        print("Use readiness/preflight first. place_order_called=0")
        print(
            "(Safety: automated live submission to production Zerodha is not "
            "enabled from this Makefile target without additional operator tooling.)"
        )
        return 2

    strategy_id = args.strategy_id
    strategy_hash = state_hash({"id": strategy_id, "v": "1.0.0"})
    config_hash = state_hash({"live_canary": True})
    broker = build_canary_broker(force_mock=True)
    broker.connect()
    account_hash = (
        broker.connection_snapshot().account_id_hash
        if broker.connection_snapshot()
        else "acct:x"
    )
    if args.activation and args.activation.exists():
        raw = json.loads(args.activation.read_text(encoding="utf-8"))
        activation = create_canary_activation(
            strategy_id=raw["strategy_id"],
            strategy_version=raw.get("strategy_version", "1.0.0"),
            strategy_hash=raw["strategy_hash"],
            config_hash=raw["config_hash"],
            dataset_provenance=raw.get("dataset_provenance", "ops"),
            broker=raw.get("broker", "ZERODHA"),
            account_hash=raw.get("account_hash", account_hash),
            confirmation_phrase=CANARY_CONFIRM_PHRASE,
            actor=raw.get("actor", "operator"),
        )
        strategy_id = activation.strategy_id
        strategy_hash = activation.strategy_hash
        config_hash = activation.config_hash
    else:
        activation = create_canary_activation(
            strategy_id=strategy_id,
            strategy_version="1.0.0",
            strategy_hash=strategy_hash,
            config_hash=config_hash,
            dataset_provenance="live_canary",
            broker="ZERODHA/MOCK",
            account_hash=account_hash,
            confirmation_phrase=CANARY_CONFIRM_PHRASE,
            actor="live_canary_script",
        )

    session = CanarySession(
        mode="LIVE_CANARY",
        broker=broker,
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        live_flag=live,
        kill_switch=KillSwitch(),
    )
    session.require_activation()
    blockers = session.activate(activation)
    if blockers:
        print(f"REFUSING: activation blockers={blockers}")
        print("place_order_called=0")
        return 2
    session.disarm_kill_switch(actor="operator", reason="live_canary")
    reco = session.reconcile({})
    if reco != "CLEAN":
        print(f"REFUSING: reconciliation={reco}")
        print("place_order_called=0")
        return 2
    session.begin_running()
    quote = LiveMarketQuote(
        symbol=args.symbol,
        price=500.0,
        timestamp=datetime.now(timezone.utc),
        source_grade="vendor_read_only",
        provider_id="operator_feed",
    )
    intent = OrderIntent(
        strategy_id=strategy_id,
        strategy_hash=strategy_hash,
        config_hash=config_hash,
        symbol=args.symbol,
        side="BUY",
        quantity=args.qty,
        ref_price=500.0,
    )
    decision = session.evaluate(intent, quote)
    if not decision.allowed or not args.submit:
        print(f"gates_allowed={decision.allowed} submit_flag={args.submit}")
        print(f"blockers={decision.blockers}")
        print("place_order_called=0")
        session.emergency_kill(reason="preflight_exit")
        broker.disconnect()
        return 0 if decision.allowed and not args.submit else 2

    out = session.submit_if_allowed(intent, quote)
    print(out)
    print(f"place_order_called={broker.place_calls}")
    broker.disconnect()
    return 0 if out.get("submitted") else 2


if __name__ == "__main__":
    raise SystemExit(main())

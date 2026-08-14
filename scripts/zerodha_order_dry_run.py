#!/usr/bin/env python3
"""Zerodha order dry-run — NEVER submits a real order."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.brokers.base import BrokerOrderRequest
from quantfund.paper.kill_switch import KillSwitch
from quantfund.production.controls import ProductionControlLimits, ProductionTradingControls
from quantfund.production.order_dry_run import dry_run_order, format_dry_run
from quantfund.trading.models import OrderSide, OrderType


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "INFY"
    qty = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    ref = float(sys.argv[3]) if len(sys.argv) > 3 else 1500.0
    req = BrokerOrderRequest(
        execution_intent_id="dryrun-intent-001",
        instrument_id=f"NSE:{symbol}",
        exchange="NSE",
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=qty,
        order_type=OrderType.MARKET,
        product="CNC",
        validity="DAY",
    )
    controls = ProductionTradingControls(
        kill_switch=KillSwitch(),
        limits=ProductionControlLimits(),
    )
    result = dry_run_order(req, ref_price=ref, controls=controls)
    print(format_dry_run(result))
    assert result.submitted is False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Controlled live activation — does NOT place orders; does NOT enable via env alone.

Usage:
  .venv/bin/python scripts/enable_live_trading.py \\
      --actor NAME \\
      --confirm I_CONFIRM_CONTROLLED_LIVE_ACTIVATION \\
      --strategy-id ID --strategy-hash H --config-hash C --risk-hash R \\
      --reason 'canary readiness' \\
      --max-order-value 5000 --max-daily-loss 1000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.production.activation import (
    ACTIVATION_CONFIRM_PHRASE,
    create_activation_record,
    evaluate_activation_gates,
    write_activation_record,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Controlled live activation (no orders).")
    p.add_argument("--actor", required=True)
    p.add_argument("--confirm", required=True, help=f"Must equal {ACTIVATION_CONFIRM_PHRASE}")
    p.add_argument("--strategy-id", required=True)
    p.add_argument("--strategy-hash", required=True)
    p.add_argument("--config-hash", required=True)
    p.add_argument("--risk-hash", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--environment", default="sandbox")
    p.add_argument("--broker-identity", default="zerodha")
    p.add_argument("--max-order-value", type=float, required=True)
    p.add_argument("--max-daily-loss", type=float, required=True)
    p.add_argument(
        "--out",
        default=str(ROOT / "data" / "activations" / "activation.json"),
    )
    args = p.parse_args()

    print("=== CONTROLLED LIVE ACTIVATION ===")
    print(f"environment: {args.environment}")
    print(f"broker: {args.broker_identity}")
    print(f"strategy_id: {args.strategy_id}")
    print(f"strategy_hash: {args.strategy_hash}")
    print(f"config_hash: {args.config_hash}")
    print(f"risk_hash: {args.risk_hash}")
    print(f"max_order_value: {args.max_order_value}")
    print(f"max_daily_loss: {args.max_daily_loss}")
    print("current_positions: (operator must review externally)")
    print()
    print("NOTE: This command does NOT place any orders.")
    print("NOTE: Environment variables alone cannot authorize live trading.")
    print()

    try:
        rec = create_activation_record(
            actor=args.actor,
            confirmation_phrase=args.confirm,
            strategy_id=args.strategy_id,
            strategy_hash=args.strategy_hash,
            config_hash=args.config_hash,
            risk_config_hash=args.risk_hash,
            broker_identity=args.broker_identity,
            reason=args.reason,
            environment=args.environment,
            max_order_value=args.max_order_value,
            max_daily_loss=args.max_daily_loss,
        )
    except ValueError as exc:
        print(f"ACTIVATION FAILED: {exc}")
        return 2

    out = Path(args.out)
    try:
        write_activation_record(out, rec)
    except FileExistsError:
        print(f"ACTIVATION FAILED: record already exists at {out}")
        return 3

    # Even after writing record, other gates may still fail — report honestly
    decision = evaluate_activation_gates(
        live_trading_enabled=True,
        broker_credentials_valid=False,
        broker_connectivity_valid=False,
        preflight_valid=False,
        reconciliation_clean=False,
        risk_config_valid=True,
        human_confirmation=True,
        strategy_explicitly_enabled=True,
        global_kill_switch_off=True,
    )
    print(f"Activation record written: {out}")
    print(f"activation_id: {rec.activation_id}")
    print(f"All gates satisfied: {decision.allowed}")
    if decision.failed_gates:
        print("Remaining gate failures:")
        for g in decision.failed_gates:
            print(f"- {g}")
    print("ORDER SUBMISSION: NOT EXECUTED")
    print("BROKER_LIVE default remains DISABLED until ALL gates pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

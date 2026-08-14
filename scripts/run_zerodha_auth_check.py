#!/usr/bin/env python3
"""Check Zerodha credentials are configured — never prints secrets; no orders."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.brokers.zerodha.auth import credentials_configured, load_credentials_from_env
from quantfund.data.providers.zerodha_historical import network_historical_allowed
from quantfund.data.zerodha_hist.envutil import merge_env_with_optional_dotenv


def main() -> int:
    merged = merge_env_with_optional_dotenv(dotenv_path=ROOT / ".env")
    for k, v in merged.items():
        if k.startswith("ZERODHA_") or k.startswith("QUANTFUND_"):
            os.environ.setdefault(k, v)
    configured = credentials_configured(merged)
    creds = load_credentials_from_env(merged)
    has_token = bool(creds and creds.access_token)
    print("ZERODHA AUTH CHECK (READ-ONLY)")
    print(f"credentials_configured={configured}")
    print(f"access_token_present={has_token}")
    print(f"network_historical_allowed={network_historical_allowed(merged)}")
    print("place_order=NOT_IMPLEMENTED_HERE")
    print("secrets_printed=false")
    # Do not print key/secret/token
    return 0 if configured and has_token else 1


if __name__ == "__main__":
    raise SystemExit(main())

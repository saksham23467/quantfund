"""Multi-year real Zerodha download — immutable packages; no yfinance fallback."""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.data.providers.zerodha_historical import (
    ZerodhaHistoricalError,
    build_zerodha_historical_provider,
)
from quantfund.data.zerodha_hist.envutil import (
    merge_env_with_optional_dotenv,
    validate_real_historical_config,
)
from quantfund.data.zerodha_hist.package import (
    next_dataset_version,
    research_zerodha_root,
    write_zerodha_dataset_package,
)
from quantfund.phase15.models import scrub_secrets
from quantfund.phase17a.ca import analyze_ca_for_symbol, default_ca_file
from quantfund.phase17a.datasets import PREFERRED_SYMBOLS
from quantfund.phase17a.quality import run_symbol_quality


BUNDLE_DATASET_ID = "zerodha_nse_daily_2018_2026"
TARGET_START = date(2018, 1, 1)
FALLBACK_STARTS = (
    date(2018, 1, 1),
    date(2019, 1, 1),
    date(2020, 1, 1),
    date(2021, 1, 1),
    date(2022, 1, 1),
    date(2023, 1, 1),
    date(2024, 1, 1),
)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def fetch_with_start_fallback(
    provider,
    symbol: str,
    *,
    end: date,
    preferred_start: date,
) -> tuple[list, date, str]:
    """Try preferred start then later years until bars appear. No other providers."""
    starts = [preferred_start] + [d for d in FALLBACK_STARTS if d > preferred_start]
    last_err = "DATA_UNAVAILABLE"
    for start in starts:
        if start > end:
            continue
        try:
            bars = provider.fetch_daily_chunked(
                symbol, start=start, end=end, chunk_days=366, sleep_s=0.35
            )
            if bars:
                return bars, start, "ok"
        except ZerodhaHistoricalError as exc:
            last_err = str(exc)[:200]
            continue
    raise ZerodhaHistoricalError(f"DATA_UNAVAILABLE:{symbol}:{last_err}")


def download_symbol_multiyear(
    *,
    symbol: str,
    provider,
    preferred_start: date,
    end: date,
    ca_file: Path | None,
    sleep_between_symbols: float = 0.5,
) -> dict[str, Any]:
    try:
        bars, used_start, _ = fetch_with_start_fallback(
            provider, symbol, end=end, preferred_start=preferred_start
        )
    except ZerodhaHistoricalError as exc:
        return {
            "symbol": symbol,
            "status": "DATA_UNAVAILABLE",
            "error": str(exc)[:200],
            "bars": 0,
        }

    quality = run_symbol_quality(bars, dataset_id=f"phase17b_{symbol.lower()}")
    ca = analyze_ca_for_symbol(symbol, ca_file=ca_file, bars=bars)
    actions = ca.pop("actions", [])
    actual_start = min(b.timestamp for b in bars).date().isoformat()
    actual_end = max(b.timestamp for b in bars).date().isoformat()
    ds_id = (
        f"zerodha_nse_daily_{symbol.lower()}_"
        f"{actual_start.replace('-', '')}_{actual_end.replace('-', '')}"
    )
    prov = provider.last_provenance().to_dict() if provider.last_provenance() else {}
    prov.update(
        {
            "phase": "17B",
            "requested_start": preferred_start.isoformat(),
            "used_start": used_start.isoformat(),
            "requested_end": end.isoformat(),
            "actual_start": actual_start,
            "actual_end": actual_end,
            "price_policy": "unknown",
            "raw_execution": True,
            "adjusted_invented": False,
        }
    )
    pkg_dir = write_zerodha_dataset_package(
        bars=bars,
        provenance=prov,
        quality_report={**quality, "ca": {k: v for k, v in ca.items() if k != "ca_meta"}},
        corporate_actions=[a.model_dump(mode="json") for a in actions],
        instrument_metadata={
            "symbol": symbol,
            "resolved": provider.resolve_instrument(symbol),
            "phase": "17B",
        },
        dataset_id=ds_id,
    )
    if sleep_between_symbols > 0:
        time.sleep(sleep_between_symbols)
    return scrub_secrets(
        {
            "symbol": symbol,
            "status": "OK",
            "bars": len(bars),
            "requested_start": preferred_start.isoformat(),
            "used_start": used_start.isoformat(),
            "requested_end": end.isoformat(),
            "actual_start": actual_start,
            "actual_end": actual_end,
            "dataset_id": ds_id,
            "dataset_version": pkg_dir.name,
            "package_dir": str(pkg_dir),
            "content_hash": json.loads((pkg_dir / "manifest.json").read_text())[
                "content_hash"
            ],
            "quality": quality,
            "corporate_actions": ca,
            "price_policy": "unknown",
        }
    )


def write_bundle_manifest(members: list[dict[str, Any]], *, version: str | None = None) -> Path:
    root = research_zerodha_root()
    ver = version or next_dataset_version(BUNDLE_DATASET_ID)
    out = root / BUNDLE_DATASET_ID / ver
    if out.exists():
        raise FileExistsError(f"dataset_immutable_refuse_overwrite:{out}")
    out.mkdir(parents=True)
    ok_members = [m for m in members if m.get("status") == "OK"]
    payload = scrub_secrets(
        {
            "dataset_id": BUNDLE_DATASET_ID,
            "dataset_version": ver,
            "phase": "17B",
            "provider": "zerodha",
            "source": "zerodha_historical_api",
            "eligibility": "DEVELOPMENT_ONLY",
            "research_eligible": False,
            "price_policy": "unknown",
            "symbols": [m["symbol"] for m in ok_members],
            "members": [
                {k: v for k, v in m.items() if k not in {"quality", "corporate_actions"}}
                for m in ok_members
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "note": "Bundle index only — member packages are immutable per-symbol datasets",
        }
    )
    (out / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return out


def download_phase17b_universe(
    *,
    symbols: tuple[str, ...] | None = None,
    start: date | None = None,
    end: date | None = None,
    force_mock: bool = False,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Download multi-year REAL Zerodha daily bars for the Phase 17 universe."""
    root = Path.cwd()
    merged = merge_env_with_optional_dotenv(env=env, dotenv_path=root / ".env")
    for k, v in merged.items():
        if k.startswith("ZERODHA_") or k.startswith("QUANTFUND_"):
            os.environ.setdefault(k, v)

    if not force_mock:
        cfg = validate_real_historical_config(merged)
        if not cfg["ok"]:
            return {
                "ok": False,
                "status": "CONFIG_BLOCKED",
                "config": cfg,
                "message": "Set QUANTFUND_ALLOW_ZERODHA_HISTORICAL=1 and ZERODHA_* in .env",
            }

    end = end or _today()
    start = start or TARGET_START
    try:
        provider = build_zerodha_historical_provider(env=merged, force_mock=force_mock)
    except ZerodhaHistoricalError as exc:
        return {
            "ok": False,
            "status": "AUTHENTICATION_FAILURE",
            "error": str(exc)[:200],
        }
    if not force_mock and provider._simulated:
        return {
            "ok": False,
            "status": "PROVIDER_SIMULATED",
            "message": "Refusing to label simulated data as Phase 17B REAL download",
        }

    ca_file = default_ca_file()
    symbols = symbols or PREFERRED_SYMBOLS
    members: list[dict[str, Any]] = []
    for sym in symbols:
        row = download_symbol_multiyear(
            symbol=sym,
            provider=provider,
            preferred_start=start,
            end=end,
            ca_file=ca_file,
        )
        members.append(row)

    ok_members = [m for m in members if m.get("status") == "OK"]
    bundle = write_bundle_manifest(members) if ok_members else None
    return scrub_secrets(
        {
            "ok": len(ok_members) > 0,
            "status": "OK" if ok_members else "DATA_UNAVAILABLE",
            "provider": "ZERODHA",
            "data": "SIMULATED" if force_mock else "REAL HISTORICAL API",
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "bundle_dataset_id": BUNDLE_DATASET_ID,
            "bundle_path": str(bundle) if bundle else None,
            "members": members,
            "orders_submitted": 0,
            "place_order_called": int(getattr(provider, "place_order_called", 0) or 0),
        }
    )

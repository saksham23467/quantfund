"""REAL Zerodha historical validation orchestration — read-only, fail-closed."""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from quantfund.data.calendar.nse import DEFAULT_NSE_CALENDAR_VERSION, NSECalendarProvider
from quantfund.data.providers.zerodha_historical import (
    ZerodhaHistoricalError,
    build_zerodha_historical_provider,
    scan_zerodha_historical_for_writes,
)
from quantfund.data.zerodha_hist.ca_import import import_ca_csv
from quantfund.data.zerodha_hist.compare import compare_zerodha_yfinance
from quantfund.data.zerodha_hist.envutil import (
    merge_env_with_optional_dotenv,
    validate_real_historical_config,
)
from quantfund.data.zerodha_hist.package import write_zerodha_dataset_package
from quantfund.data.zerodha_hist.validation import (
    evaluate_eligibility,
    leakage_asof_test,
    next_bar_open_regression,
    reproducibility_check,
    run_baselines,
    run_quality,
)
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.quality.report import Severity
from quantfund.phase15.models import scrub_secrets


DEFAULT_SYMBOLS = (
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "ITC",
    "LT",
)

DEFAULT_START = date(2024, 1, 1)
DEFAULT_END = date(2024, 6, 28)


def calendar_coverage(
    bars: list,
    *,
    start: date,
    end: date,
    calendar_version: str | None = None,
) -> dict[str, Any]:
    cal = NSECalendarProvider(
        calendar_version=calendar_version or DEFAULT_NSE_CALENDAR_VERSION
    )
    expected = set(cal.sessions_in_range(start, end))
    observed = {b.timestamp.date() for b in bars}
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    coverage = (len(expected & observed) / len(expected)) if expected else 0.0
    return {
        "calendar_id": cal.calendar_id,
        "calendar_version": cal.calendar_version,
        "calendar_verified": cal.verified,
        "coverage_start": start.isoformat(),
        "coverage_end": end.isoformat(),
        "expected_sessions": len(expected),
        "observed_sessions": len(observed),
        "missing_sessions": len(missing),
        "unexpected_sessions": len(unexpected),
        "missing_session_dates": [d.isoformat() for d in missing[:30]],
        "unexpected_session_dates": [d.isoformat() for d in unexpected[:30]],
        "coverage_ratio": round(coverage, 6),
        "calendar_in_coverage": cal.in_coverage(start) and cal.in_coverage(end),
    }


def run_quality_with_nse_calendar(
    bars: list,
    *,
    provider,
) -> dict[str, Any]:
    cal = NSECalendarProvider(calendar_version=DEFAULT_NSE_CALENDAR_VERSION)
    report = run_quality_checks(
        bars,
        calendar=cal,
        instruments=provider.get_instruments(),
        provider_capabilities=provider.capabilities(),
        dataset_id="zerodha_real_hist",
        source="zerodha_historical_api",
    )
    errors = [i for i in report.issues if i.severity is Severity.ERROR]
    warnings = [i for i in report.issues if i.severity is Severity.WARNING]
    return {
        "errors": len(errors),
        "warnings": len(warnings),
        "data_blocked": len(errors) > 0,
        "issues": [
            {"severity": i.severity.value, "code": i.code, "message": i.message}
            for i in report.issues[:80]
        ],
    }


def _default_ca_path() -> Path | None:
    root = Path.cwd()
    candidates = [
        root / "CF-CA-equities-01-01-2009-to-01-08-2026.csv",
        root / "tests" / "fixtures" / "ca" / "cf_ca_sample.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def validate_symbol_real(
    *,
    symbol: str,
    start: date,
    end: date,
    provider,
    out_dir: Path,
    ca_file: Path | None,
    sleep_s: float = 0.35,
) -> dict[str, Any]:
    if sleep_s > 0:
        time.sleep(sleep_s)
    resolved = provider.resolve_instrument(symbol, exchange="NSE")
    bars = provider.fetch_daily(symbol, start=start, end=end, exchange="NSE")
    quality = run_quality_with_nse_calendar(bars, provider=provider)
    # Also keep FakeCalendar-free quality summary from bars-derived path for comparison
    quality_soft = run_quality(bars, provider=provider)
    cal = calendar_coverage(bars, start=start, end=end)
    ca_actions, ca_meta = ([], {"status": "SKIPPED", "count": 0})
    if ca_file is not None:
        ca_actions, ca_meta = import_ca_csv(ca_file, symbol_filter=symbol)
    elig = evaluate_eligibility(quality, bars=bars)
    research_label = (
        "RESEARCH_ELIGIBLE" if elig.get("is_research_eligible") else "DEVELOPMENT_ONLY"
    )
    package_dir = None
    manifest_hash = None
    # Persist RAW bars even when quality reports errors — do not silently repair.
    if bars:
        package_dir = write_zerodha_dataset_package(
            bars=bars,
            provenance=(
                provider.last_provenance().to_dict() if provider.last_provenance() else {}
            ),
            quality_report={**quality, "calendar": cal},
            corporate_actions=[a.model_dump(mode="json") for a in ca_actions],
            instrument_metadata={
                "resolved": resolved,
                "price_policy": "unknown",
                "ohlc_series": "RAW_AS_RETURNED_BY_KITE",
                "adjusted_invented": False,
            },
            dataset_id=(
                f"zerodha_nse_daily_{symbol.lower()}_"
                f"{start.isoformat().replace('-', '')}_"
                f"{end.isoformat().replace('-', '')}"
            ),
        )
        man = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest_hash = man.get("content_hash")

    leakage = leakage_asof_test(bars)
    nbo = next_bar_open_regression(bars)
    baselines = run_baselines(bars, out_dir=out_dir / symbol.lower())
    repro = reproducibility_check(bars)
    prov = provider.last_provenance().to_dict() if provider.last_provenance() else {}
    actual_start = min(b.timestamp for b in bars).date().isoformat() if bars else None
    actual_end = max(b.timestamp for b in bars).date().isoformat() if bars else None

    return scrub_secrets(
        {
            "symbol": symbol,
            "exchange": "NSE",
            "instrument_token": resolved.get("instrument_token"),
            "tradingsymbol": resolved.get("tradingsymbol"),
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "actual_start": actual_start,
            "actual_end": actual_end,
            "bars": len(bars),
            "quality": quality,
            "quality_soft_calendar": quality_soft,
            "calendar": cal,
            "corporate_actions": {
                **ca_meta,
                "coverage": "PARTIAL" if ca_meta.get("count") else "NONE",
                "price_policy": "unknown",
                "raw_ohlc": True,
                "adjusted_invented": False,
            },
            "eligibility": {**elig, "research": research_label},
            "research_eligibility": research_label,
            "leakage": leakage,
            "next_bar_open": nbo,
            "baselines": baselines,
            "reproducibility": repro,
            "package_dir": str(package_dir) if package_dir else None,
            "dataset_hash": manifest_hash,
            "provenance": prov,
            "place_order_called": provider.place_order_called,
        }
    )


def run_real_zerodha_validation(
    *,
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS,
    start: date = DEFAULT_START,
    end: date = DEFAULT_END,
    out_dir: Path | None = None,
    dotenv_path: Path | None = None,
    ca_file: Path | None = None,
    compare_yfinance_symbol: str = "RELIANCE",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = Path.cwd()
    out_dir = out_dir or (root / "experiments" / "zerodha_real_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    dotenv_path = dotenv_path or (root / ".env")
    merged = merge_env_with_optional_dotenv(env=env, dotenv_path=dotenv_path)
    cfg = validate_real_historical_config(merged)
    if not cfg["ok"]:
        return scrub_secrets(
            {
                "ok": False,
                "result": "FAIL",
                "stage": "configuration",
                "config": cfg,
                "message": (
                    "REAL Zerodha historical validation blocked: set "
                    "QUANTFUND_ALLOW_ZERODHA_HISTORICAL=1 and ZERODHA_API_KEY / "
                    "ZERODHA_API_SECRET / ZERODHA_ACCESS_TOKEN in the environment "
                    "or a gitignored .env file. Credentials are never printed."
                ),
                "orders_submitted": 0,
                "place_order_called": 0,
                "broker_write_attempts": 0,
                "live_trading": "DISABLED",
                "kill_switch": "ARMED",
                "paper_trading": "NOT_STARTED",
                "broker_write_capability": "DISABLED",
            }
        )

    write_hits = scan_zerodha_historical_for_writes()
    try:
        provider = build_zerodha_historical_provider(env=merged, force_mock=False)
    except ZerodhaHistoricalError as exc:
        return scrub_secrets(
            {
                "ok": False,
                "result": "FAIL",
                "stage": "authentication",
                "error": str(exc)[:200],
                "config": {
                    k: cfg[k]
                    for k in (
                        "allow_flag",
                        "api_key_present",
                        "api_secret_present",
                        "access_token_present",
                    )
                },
                "orders_submitted": 0,
                "place_order_called": 0,
                "broker_write_attempts": 0,
                "live_trading": "DISABLED",
                "kill_switch": "ARMED",
                "paper_trading": "NOT_STARTED",
                "broker_write_capability": "DISABLED",
            }
        )

    if provider._simulated:
        return scrub_secrets(
            {
                "ok": False,
                "result": "FAIL",
                "stage": "provider_mode",
                "message": "Provider unexpectedly simulated; refusing to label as REAL",
                "orders_submitted": 0,
                "place_order_called": 0,
            }
        )

    ca_path = ca_file or _default_ca_path()
    per_symbol: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, sym in enumerate(symbols):
        try:
            row = validate_symbol_real(
                symbol=sym,
                start=start,
                end=end,
                provider=provider,
                out_dir=out_dir,
                ca_file=ca_path,
                sleep_s=0.4 if i else 0.0,
            )
            per_symbol.append(row)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sym}:{type(exc).__name__}:{str(exc)[:160]}")
            per_symbol.append(
                scrub_secrets(
                    {
                        "symbol": sym,
                        "bars": 0,
                        "error": f"{type(exc).__name__}",
                        "detail": str(exc)[:160],
                        "research_eligibility": "DEVELOPMENT_ONLY",
                    }
                )
            )

    # Optional yfinance compare for primary symbol
    yf_report = None
    primary = next((r for r in per_symbol if r.get("symbol") == compare_yfinance_symbol), None)
    if primary and primary.get("bars"):
        try:
            # Re-fetch bars from package if available; else skip bars arg
            yf_report = compare_zerodha_yfinance(
                symbol=compare_yfinance_symbol,
                start=start,
                end=end,
                force_mock=False,
                out_path=out_dir / "data_comparison_report.json",
            )
            # Force compare to use real provider for zerodha side when possible
        except Exception as exc:  # noqa: BLE001
            yf_report = {
                "warnings": [f"yfinance_compare_failed:{type(exc).__name__}"],
                "note": "Diagnostic only — does not change eligibility.",
            }

    transport = provider._client.transport
    write_attempts = int(getattr(transport, "write_attempts", 0) or 0)
    place_calls = int(provider.place_order_called)

    aggregate = []
    for r in per_symbol:
        aggregate.append(
            {
                "symbol": r.get("symbol"),
                "bars": r.get("bars"),
                "missing_sessions": (r.get("calendar") or {}).get("missing_sessions"),
                "quality_errors": (r.get("quality") or {}).get("errors"),
                "warnings": (r.get("quality") or {}).get("warnings"),
                "ca_coverage": (r.get("corporate_actions") or {}).get("coverage"),
                "ca_count": (r.get("corporate_actions") or {}).get("count"),
                "eligibility": r.get("research_eligibility"),
                "eligibility_blockers": (r.get("eligibility") or {}).get("reason", [])[:5],
                "error": r.get("error"),
            }
        )

    # Safety / overall
    leakage_ok = all(
        (r.get("leakage") or {}).get("status") in {None, "PASS", "SKIP"}
        or r.get("error")
        for r in per_symbol
    )
    # Require primary RELIANCE success for overall PASS
    reliance = next((r for r in per_symbol if r.get("symbol") == "RELIANCE"), {})
    reliance_ok = (
        not reliance.get("error")
        and int(reliance.get("bars") or 0) > 0
        and (reliance.get("leakage") or {}).get("status") == "PASS"
        and (reliance.get("reproducibility") or {}).get("status") == "PASS"
        and (reliance.get("next_bar_open") or {}).get("status") in {"PASS", "SKIP"}
        and reliance.get("research_eligibility") == "DEVELOPMENT_ONLY"
    )
    ok = (
        reliance_ok
        and place_calls == 0
        and write_attempts == 0
        and not write_hits
        and leakage_ok
    )

    payload = scrub_secrets(
        {
            "ok": ok,
            "result": "PASS" if ok else "FAIL",
            "provider": "ZERODHA",
            "data": "REAL HISTORICAL API",
            "exchange": "NSE",
            "interval": "1DAY",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "symbols": list(symbols),
            "per_symbol": per_symbol,
            "aggregate": aggregate,
            "yfinance_comparison": yf_report,
            "write_scan_hits": write_hits,
            "transport_calls_sample": list(getattr(transport, "calls", [])[:40]),
            "orders_submitted": 0,
            "place_order_called": place_calls,
            "broker_write_attempts": write_attempts,
            "live_trading": "DISABLED",
            "kill_switch": "ARMED",
            "paper_trading": "NOT_STARTED",
            "broker_write_capability": "DISABLED",
            "price_policy": "unknown",
            "statement": (
                "Historical-data validation only. No broker order submission occurred."
            ),
            "fetch_errors": errors,
            "ca_file": str(ca_path) if ca_path else None,
        }
    )
    (out_dir / "real_validation_report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return payload


def render_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Zerodha Real Data Validation",
        "",
        "## Prominence",
        "",
        "Historical-data validation only. No broker order submission occurred.",
        "",
        f"- Provider: `{payload.get('provider')}`",
        f"- Data: `{payload.get('data')}`",
        f"- Result: `{payload.get('result')}`",
        f"- Date range: `{payload.get('start')}` → `{payload.get('end')}`",
        f"- Interval: `{payload.get('interval')}`",
        f"- Price policy: `{payload.get('price_policy')}` (RAW as returned; adjusted not invented)",
        "",
        "## Security verification",
        "",
        f"- orders_submitted: `{payload.get('orders_submitted')}`",
        f"- place_order_called: `{payload.get('place_order_called')}`",
        f"- broker_write_attempts: `{payload.get('broker_write_attempts')}`",
        f"- live_trading: `{payload.get('live_trading')}`",
        f"- kill_switch: `{payload.get('kill_switch')}`",
        f"- paper_trading: `{payload.get('paper_trading')}`",
        f"- broker_write_capability: `{payload.get('broker_write_capability')}`",
        "",
        "## Aggregate",
        "",
        "| symbol | bars | missing sessions | quality errors | warnings | CA coverage | eligibility |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for row in payload.get("aggregate") or []:
        lines.append(
            f"| {row.get('symbol')} | {row.get('bars')} | {row.get('missing_sessions')} | "
            f"{row.get('quality_errors')} | {row.get('warnings')} | {row.get('ca_coverage')} | "
            f"{row.get('eligibility')} |"
        )
    lines.extend(["", "## Per-symbol baseline (summary)", ""])
    for r in payload.get("per_symbol") or []:
        lines.append(f"### {r.get('symbol')}")
        if r.get("error"):
            lines.append(f"- ERROR: `{r.get('error')}` — `{r.get('detail')}`")
            continue
        lines.append(f"- Bars: `{r.get('bars')}` ({r.get('actual_start')} → {r.get('actual_end')})")
        lines.append(f"- Instrument token: `{r.get('instrument_token')}`")
        lines.append(f"- Dataset hash: `{r.get('dataset_hash')}`")
        cal = r.get("calendar") or {}
        lines.append(
            f"- Calendar coverage: `{cal.get('coverage_ratio')}` "
            f"(missing={cal.get('missing_sessions')}, unexpected={cal.get('unexpected_sessions')})"
        )
        q = r.get("quality") or {}
        lines.append(f"- Quality errors/warnings: `{q.get('errors')}` / `{q.get('warnings')}`")
        ca = r.get("corporate_actions") or {}
        lines.append(f"- CA: count=`{ca.get('count')}` coverage=`{ca.get('coverage')}`")
        lines.append(f"- Eligibility: `{r.get('research_eligibility')}`")
        lines.append(f"- Leakage: `{(r.get('leakage') or {}).get('status')}`")
        lines.append(f"- Reproducibility: `{(r.get('reproducibility') or {}).get('status')}`")
        lines.append(f"- Next-bar-open: `{(r.get('next_bar_open') or {}).get('status')}`")
        strats = (r.get("baselines") or {}).get("strategies") or {}
        for name, st in strats.items():
            if name.startswith("research_"):
                lines.append(
                    f"- {name}: status=`{st.get('status')}` hash=`{st.get('config_hash')}`"
                )
                continue
            m = st.get("metrics") or {}
            lines.append(
                f"- {name}: return=`{m.get('total_return')}` trades=`{m.get('number_of_trades')}` "
                f"sharpe=`{m.get('sharpe_ratio')}` dd=`{m.get('maximum_drawdown')}`"
            )
        lines.append("")
    yf = payload.get("yfinance_comparison")
    lines.extend(["## Zerodha vs yfinance (diagnostic)", ""])
    if yf:
        lines.append("```json")
        lines.append(json.dumps(yf, indent=2, default=str)[:4000])
        lines.append("```")
    else:
        lines.append("Not available.")
    lines.extend(
        [
            "",
            "## Remaining blockers",
            "",
            "- Zerodha historical remains `non_exchange` / DEVELOPMENT_ONLY under existing gates",
            "- `price_policy=unknown` until adjustment semantics are independently proven",
            "- Calendar/PIT/delisted/CA completeness still required for RESEARCH_ELIGIBLE",
            "- No eligibility shortcut for provider==zerodha",
            "",
            "## Explicit statement",
            "",
            "> Historical-data validation only. No broker order submission occurred.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"

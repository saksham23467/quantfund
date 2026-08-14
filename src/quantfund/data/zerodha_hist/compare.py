"""Optional Zerodha vs yfinance comparison — diagnostic only, no eligibility change."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.data.models import MarketBar
from quantfund.data.providers.zerodha_historical import build_zerodha_historical_provider
from quantfund.phase15.models import scrub_secrets


def _index(bars: list[MarketBar]) -> dict[date, MarketBar]:
    out: dict[date, MarketBar] = {}
    for b in bars:
        out[b.timestamp.date()] = b
    return out


def compare_zerodha_yfinance(
    *,
    symbol: str = "RELIANCE",
    start: date,
    end: date,
    zerodha_bars: list[MarketBar] | None = None,
    yfinance_bars: list[MarketBar] | None = None,
    out_path: Path | None = None,
    force_mock: bool = True,
) -> dict[str, Any]:
    if zerodha_bars is None:
        p = build_zerodha_historical_provider(force_mock=force_mock)
        zerodha_bars = p.fetch_daily(symbol, start=start, end=end)

    if yfinance_bars is None:
        try:
            from quantfund.data.providers.yfinance_provider import YFinanceProvider

            yf = YFinanceProvider()
            yfinance_bars = yf.get_history(
                f"{symbol}.NS",
                start=datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
                end=datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
            )
            # normalize symbol
            yfinance_bars = [
                MarketBar(
                    timestamp=b.timestamp,
                    symbol=symbol,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                    instrument_id=f"NSE:{symbol}",
                )
                for b in yfinance_bars
            ]
        except Exception as exc:  # noqa: BLE001
            report = {
                "symbol": symbol,
                "date_range": {"start": start.isoformat(), "end": end.isoformat()},
                "zerodha_rows": len(zerodha_bars),
                "yfinance_rows": 0,
                "common_rows": 0,
                "zerodha_only_rows": len(zerodha_bars),
                "yfinance_only_rows": 0,
                "ohlc_differences": 0,
                "volume_differences": 0,
                "warnings": [f"yfinance_unavailable:{type(exc).__name__}"],
                "note": "Diagnostic only — does not change eligibility.",
            }
            if out_path:
                out_path.write_text(
                    json.dumps(scrub_secrets(report), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            return report

    z = _index(zerodha_bars)
    y = _index(yfinance_bars or [])
    common = sorted(set(z) & set(y))
    z_only = sorted(set(z) - set(y))
    y_only = sorted(set(y) - set(z))
    ohlc_diff = 0
    vol_diff = 0
    for d in common:
        zb, yb = z[d], y[d]
        if any(
            abs(getattr(zb, k) - getattr(yb, k)) > 1e-6
            for k in ("open", "high", "low", "close")
        ):
            ohlc_diff += 1
        if abs(zb.volume - yb.volume) > 1e-6:
            vol_diff += 1

    report = {
        "symbol": symbol,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "zerodha_rows": len(z),
        "yfinance_rows": len(y),
        "common_rows": len(common),
        "zerodha_only_rows": len(z_only),
        "yfinance_only_rows": len(y_only),
        "ohlc_differences": ohlc_diff,
        "volume_differences": vol_diff,
        "warnings": [
            "Do not declare either source correct solely because values differ.",
            "Eligibility unchanged.",
        ],
        "note": "Diagnostic only — does not change eligibility.",
    }
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(scrub_secrets(report), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report

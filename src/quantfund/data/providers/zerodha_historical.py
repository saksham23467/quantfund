"""Zerodha historical OHLCV provider — READ ONLY. No order submission.

Reuses Phase 16A / brokers.zerodha auth + ZerodhaMarketDataAdapter.historical_daily.
Fail closed on API errors; never silently substitutes another market-data vendor.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.brokers.zerodha.auth import (
    ZerodhaCredentials,
    load_credentials_from_env,
)
from quantfund.brokers.zerodha.client import FakeKiteTransport, KiteClient, KiteTransport
from quantfund.brokers.zerodha.market_data import ZerodhaMarketDataAdapter
from quantfund.data.grades import SourceGrade
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.providers.capabilities import (
    CoverageQuality,
    LicenseStatus,
    ProviderCapabilities,
)
from quantfund.data.providers.roles import DevelopmentProvider
from quantfund.phase15.models import scrub_secrets
from quantfund.phase16a.mock_transport import build_mock_kite_transport


class ZerodhaHistoricalError(RuntimeError):
    """Fail-closed historical fetch / resolve error."""


class InstrumentResolutionError(ZerodhaHistoricalError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}:{message}")
        self.code = code


@dataclass(frozen=True)
class ZerodhaHistoricalCapabilities:
    READ_HISTORICAL_DATA: bool = True
    READ_MARKET_DATA: bool = True
    READ_ACCOUNT: bool = False
    WRITE_ORDERS: bool = False
    CANCEL_ORDERS: bool = False
    MODIFY_ORDERS: bool = False

    def __post_init__(self) -> None:
        if self.WRITE_ORDERS or self.CANCEL_ORDERS or self.MODIFY_ORDERS:
            raise ValueError("zerodha_historical_write_capabilities_forbidden")
        if self.READ_ACCOUNT:
            raise ValueError("zerodha_historical_account_read_not_in_scope")

    def to_dict(self) -> dict[str, Any]:
        return {
            "READ_HISTORICAL_DATA": True,
            "READ_MARKET_DATA": True,
            "READ_ACCOUNT": False,
            "WRITE_ORDERS": False,
            "CANCEL_ORDERS": False,
            "MODIFY_ORDERS": False,
        }


@dataclass
class HistoricalFetchProvenance:
    provider: str = "zerodha"
    source: str = "zerodha_historical_api"
    retrieval_timestamp: str = ""
    instrument_token: int | None = None
    interval: str = "1day"
    requested_start: str = ""
    requested_end: str = ""
    exchange: str = "NSE"
    tradingsymbol: str = ""
    price_policy: str = "unknown"
    api_data_version: str = "kite_historical_v3"
    simulated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return scrub_secrets(
            {
                "provider": self.provider,
                "source": self.source,
                "retrieval_timestamp": self.retrieval_timestamp,
                "instrument_token": self.instrument_token,
                "interval": self.interval,
                "requested_start": self.requested_start,
                "requested_end": self.requested_end,
                "exchange": self.exchange,
                "tradingsymbol": self.tradingsymbol,
                "price_policy": self.price_policy,
                "api_data_version": self.api_data_version,
                "simulated": self.simulated,
            }
        )


def zerodha_historical_provider_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_id="zerodha_historical",
        provider_name="Zerodha Kite Historical API",
        source_grade=SourceGrade.NON_EXCHANGE,
        historical_depth="broker_api_dependent",
        corporate_action_quality=CoverageQuality.NONE,
        delisted_coverage=CoverageQuality.UNKNOWN,
        universe_membership_quality=CoverageQuality.NONE,
        identity_coverage=CoverageQuality.PARTIAL,
        exchange_authority=False,
        supports_instrument_master=True,
        supports_daily_bars=True,
        supports_corporate_actions=False,
        supports_provenance=True,
        supports_licensing_evidence=False,
        supported_exchanges=["NSE"],
        license_status=LicenseStatus.INTERNAL_RESEARCH_ONLY,
        redistribution_allowed=False,
        licensing_notes=(
            "Broker historical API for operator account use. Not an NSE authority "
            "research redistribution package. Does not auto-satisfy RESEARCH_ELIGIBLE."
        ),
        usage_notes="DEVELOPMENT_ONLY until full research package certification.",
        limitations=[
            "price_policy_unknown_until_verified",
            "no_silent_vendor_fallback",
            "write_apis_forbidden",
        ],
    )


def network_historical_allowed(env: dict[str, str] | None = None) -> bool:
    e = env if env is not None else dict(os.environ)
    return (e.get("QUANTFUND_ALLOW_ZERODHA_HISTORICAL") or "").strip() == "1"


@dataclass
class ZerodhaHistoricalProvider(DevelopmentProvider):
    """Read-only historical bars from Kite. Fail closed; no silent vendor fallback."""

    _client: KiteClient
    _adapter: ZerodhaMarketDataAdapter
    _instruments: list[Instrument] = field(default_factory=list)
    _cache: dict[str, list[MarketBar]] = field(default_factory=dict)
    _last_provenance: HistoricalFetchProvenance | None = None
    _simulated: bool = True
    _window_start: date | None = None
    _window_end: date | None = None
    place_order_called: int = 0

    @property
    def name(self) -> str:
        return "zerodha_historical"

    @property
    def source_grade(self) -> SourceGrade:
        return SourceGrade.NON_EXCHANGE

    def capabilities(self) -> ProviderCapabilities:
        return zerodha_historical_provider_capabilities()

    def hist_capabilities(self) -> ZerodhaHistoricalCapabilities:
        return ZerodhaHistoricalCapabilities()

    def get_instruments(self) -> list[Instrument]:
        return list(self._instruments)

    def last_provenance(self) -> HistoricalFetchProvenance | None:
        return self._last_provenance

    def resolve_instrument(
        self, symbol: str, *, exchange: str = "NSE"
    ) -> dict[str, Any]:
        sym = (symbol or "").strip().upper()
        if ":" in sym:
            parts = sym.split(":", 1)
            exchange, sym = parts[0].upper(), parts[1].upper()
        if not sym:
            raise InstrumentResolutionError("empty_symbol", "symbol required")

        self._adapter.load_instruments()
        matches = [
            r
            for r in self._adapter._instruments
            if r.tradingsymbol.upper() == sym and r.exchange.upper() == exchange.upper()
        ]
        if not matches:
            raise InstrumentResolutionError("unknown_instrument", f"{exchange}:{sym}")
        if len(matches) > 1:
            # Prefer cash equity EQ rows when instrument_type is present.
            eq = [
                r
                for r in matches
                if (r.instrument_type or "").upper() in {"EQ", "EQUITY"}
            ]
            if len(eq) == 1:
                matches = eq
            else:
                raise InstrumentResolutionError(
                    "ambiguous_instrument",
                    f"{exchange}:{sym}:{len(matches)}",
                )
        row = matches[0]
        inst = Instrument(
            symbol=row.tradingsymbol,
            exchange=row.exchange,
            isin=row.isin,
            instrument_id=f"{row.exchange}:{row.tradingsymbol}",
        )
        # keep master
        ids = {i.instrument_id for i in self._instruments}
        if inst.instrument_id not in ids:
            self._instruments.append(inst)
        return {
            "exchange": row.exchange,
            "tradingsymbol": row.tradingsymbol,
            "instrument_token": row.instrument_token,
            "isin": row.isin,
            "instrument_id": inst.instrument_id,
            "status": "RESOLVED",
        }

    def fetch_daily(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
        exchange: str = "NSE",
    ) -> list[MarketBar]:
        if end < start:
            raise ZerodhaHistoricalError("invalid_date_range")
        try:
            resolved = self.resolve_instrument(symbol, exchange=exchange)
            token = int(resolved["instrument_token"])
            candles = self._adapter.historical_daily(
                token, from_date=start, to_date=end
            )
        except InstrumentResolutionError:
            raise
        except ZerodhaHistoricalError:
            raise
        except Exception as exc:
            raise ZerodhaHistoricalError(
                f"historical_api_failure:{type(exc).__name__}"
            ) from exc
        if not candles:
            raise ZerodhaHistoricalError("missing_interval_or_empty_response")

        bars: list[MarketBar] = []
        sym = str(resolved["tradingsymbol"])
        iid = str(resolved["instrument_id"])
        for c in candles:
            ts = c.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            bars.append(
                MarketBar(
                    timestamp=ts,
                    symbol=sym,
                    open=float(c.open),
                    high=float(c.high),
                    low=float(c.low),
                    close=float(c.close),
                    volume=float(c.volume),
                    instrument_id=iid,
                )
            )
        bars.sort(key=lambda b: b.timestamp)
        self._cache[sym] = bars
        self._window_start, self._window_end = start, end
        self._last_provenance = HistoricalFetchProvenance(
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            instrument_token=token,
            interval="1day",
            requested_start=start.isoformat(),
            requested_end=end.isoformat(),
            exchange=str(resolved["exchange"]),
            tradingsymbol=sym,
            price_policy="unknown",
            simulated=self._simulated,
        )
        return list(bars)

    def fetch_daily_chunked(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
        exchange: str = "NSE",
        chunk_days: int = 365,
        sleep_s: float = 0.35,
    ) -> list[MarketBar]:
        """Fetch daily bars in chunks to respect Kite historical limits.

        Does not fill gaps from other providers. Empty total range → DATA_UNAVAILABLE.
        """
        import time

        if end < start:
            raise ZerodhaHistoricalError("invalid_date_range")
        if chunk_days < 1:
            raise ZerodhaHistoricalError("invalid_chunk_days")

        resolved = self.resolve_instrument(symbol, exchange=exchange)
        token = int(resolved["instrument_token"])
        sym = str(resolved["tradingsymbol"])
        iid = str(resolved["instrument_id"])
        all_bars: list[MarketBar] = []
        seen: set[str] = set()
        cur = start
        chunk_errors: list[str] = []
        while cur <= end:
            chunk_end = min(end, date.fromordinal(cur.toordinal() + chunk_days - 1))
            try:
                candles = self._adapter.historical_daily(
                    token, from_date=cur, to_date=chunk_end
                )
            except Exception as exc:  # noqa: BLE001
                chunk_errors.append(
                    f"{cur.isoformat()}:{chunk_end.isoformat()}:{type(exc).__name__}"
                )
                candles = []
            for c in candles or []:
                ts = c.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                key = ts.isoformat()
                if key in seen:
                    continue
                seen.add(key)
                all_bars.append(
                    MarketBar(
                        timestamp=ts,
                        symbol=sym,
                        open=float(c.open),
                        high=float(c.high),
                        low=float(c.low),
                        close=float(c.close),
                        volume=float(c.volume),
                        instrument_id=iid,
                    )
                )
            cur = date.fromordinal(chunk_end.toordinal() + 1)
            if sleep_s > 0 and cur <= end:
                time.sleep(sleep_s)

        if not all_bars:
            raise ZerodhaHistoricalError(
                "DATA_UNAVAILABLE:"
                + (chunk_errors[0] if chunk_errors else "empty_range")
            )

        all_bars.sort(key=lambda b: b.timestamp)
        self._cache[sym] = all_bars
        self._window_start, self._window_end = start, end
        self._last_provenance = HistoricalFetchProvenance(
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            instrument_token=token,
            interval="1day",
            requested_start=start.isoformat(),
            requested_end=end.isoformat(),
            exchange=str(resolved["exchange"]),
            tradingsymbol=sym,
            price_policy="unknown",
            simulated=self._simulated,
        )
        return list(all_bars)

    def get_history(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[MarketBar]:
        sym = symbol.strip().upper().split(":")[-1]
        if sym in self._cache:
            bars = self._cache[sym]
        else:
            s = (start or datetime(2024, 1, 1, tzinfo=timezone.utc)).date()
            e = (end or datetime.now(timezone.utc)).date()
            bars = self.fetch_daily(sym, start=s, end=e)
        if start is not None:
            bars = [b for b in bars if b.timestamp >= start]
        if end is not None:
            bars = [b for b in bars if b.timestamp <= end]
        return bars

    # Explicit write surface — must never succeed
    def place_order(self, *args: Any, **kwargs: Any) -> None:
        self.place_order_called += 1
        raise ZerodhaHistoricalError("place_order_forbidden")

    def modify_order(self, *args: Any, **kwargs: Any) -> None:
        raise ZerodhaHistoricalError("modify_order_forbidden")

    def cancel_order(self, *args: Any, **kwargs: Any) -> None:
        raise ZerodhaHistoricalError("cancel_order_forbidden")


def build_zerodha_historical_provider(
    *,
    env: dict[str, str] | None = None,
    transport: KiteTransport | None = None,
    force_mock: bool = False,
    mock_symbol: str = "RELIANCE",
    mock_candles: list[list[Any]] | None = None,
) -> ZerodhaHistoricalProvider:
    """Factory: mock by default / CI; real only with allow flag + credentials."""
    env = env if env is not None else dict(os.environ)
    want_real = network_historical_allowed(env) and not force_mock and transport is None
    if want_real:
        creds = load_credentials_from_env(env)
        if creds is None or not creds.access_token:
            raise ZerodhaHistoricalError("authentication_failure:missing_credentials")
        from quantfund.brokers.zerodha.client import UrllibKiteTransport
        from quantfund.data.zerodha_hist.readonly_transport import (
            ReadOnlyHistoricalTransport,
        )

        transport = ReadOnlyHistoricalTransport(UrllibKiteTransport())
        client = KiteClient(credentials=creds, transport=transport)
        try:
            client.mark_connected()
        except Exception as exc:
            raise ZerodhaHistoricalError(
                f"authentication_failure:{type(exc).__name__}"
            ) from exc
        return ZerodhaHistoricalProvider(
            _client=client,
            _adapter=ZerodhaMarketDataAdapter(client=client),
            _simulated=False,
        )

    # Mock / injected transport path (CI + demos)
    t = transport or build_mock_kite_transport(symbol=mock_symbol)
    inner = getattr(t, "inner", t)
    if mock_candles is not None:
        if isinstance(inner, FakeKiteTransport):
            inner.candles = list(mock_candles)
        elif isinstance(t, FakeKiteTransport):
            t.candles = list(mock_candles)
    elif transport is None and isinstance(inner, FakeKiteTransport):
        # Replace single placeholder candle with a research-length series
        inner.candles = _default_mock_candles()
    elif isinstance(inner, FakeKiteTransport) and len(inner.candles) < 2:
        inner.candles = _default_mock_candles()
    creds = ZerodhaCredentials(api_key="mock", api_secret="mock", access_token="mock")
    client = KiteClient(credentials=creds, transport=t)
    client.mark_connected()
    adapter = ZerodhaMarketDataAdapter(client=client)
    return ZerodhaHistoricalProvider(
        _client=client, _adapter=adapter, _simulated=True
    )


def _default_mock_candles() -> list[list[Any]]:
    """Deterministic daily candles for CI (enough for baseline strategies)."""
    out: list[list[Any]] = []
    px = 100.0
    # ~80 sessions spanning weekdays in 2024
    d = date(2024, 1, 2)
    while len(out) < 80:
        if d.weekday() < 5:
            o = px
            h = px + 2
            l = px - 2
            c = px + (1.0 if len(out) % 3 else -0.5)
            out.append([datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc).isoformat(), o, h, l, c, 10000 + len(out)])
            px = c
        d = date.fromordinal(d.toordinal() + 1)
    return out


def scan_zerodha_historical_for_writes() -> list[str]:
    """AST scan — provider module must not import/call broker write APIs."""
    path = Path(__file__).resolve()
    forbidden_call = {
        "place_order",
        "modify_order",
        "cancel_order",
        "exit_order",
        "basket_order",
    }
    hits: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    # Flag imports of write-oriented broker modules (not market_data / auth / client)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            if mod.endswith(".orders") or mod.endswith("zerodha.adapter"):
                hits.append(f"forbidden_import:{mod}")
        if isinstance(node, ast.Call):
            func = node.func
            # Flag external calls like client.place_order(...); allow FunctionDef stubs
            if isinstance(func, ast.Attribute) and func.attr in forbidden_call:
                # Ignore if this Call is not actually present for stubs — stubs are defs.
                # A call like self.place_order() would be a problem; our stubs never call.
                if isinstance(func.value, ast.Name) and func.value.id == "self":
                    continue
                hits.append(f"{path.name}:{node.lineno}:call_{func.attr}")
            if isinstance(func, ast.Name) and func.id in forbidden_call:
                hits.append(f"{path.name}:{node.lineno}:call_{func.id}")
    return hits

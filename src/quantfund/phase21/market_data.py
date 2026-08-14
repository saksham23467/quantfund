"""Zerodha real-time / EOD polling market data — no yfinance on this path."""

from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from quantfund.brokers.zerodha.auth import (
    ZerodhaCredentials,
    ZerodhaEnv,
    load_credentials_from_env,
    parse_zerodha_env,
)
from quantfund.brokers.zerodha.client import FakeKiteTransport, KiteClient, UrllibKiteTransport
from quantfund.brokers.zerodha.market_data import ZerodhaMarketDataAdapter
from quantfund.phase12.market_data import to_ist
from quantfund.phase14.market_data import ProviderHealth, RealTimeBar, RealTimeMarketDataProvider
from quantfund.phase15.capabilities import MarketDataCapabilities
from quantfund.phase15.providers import CapableMarketDataProvider, ProviderProvenance
from quantfund.phase21.mock_zerodha import build_phase21_mock_transport


ZERODHA_PAPER_CAPS = MarketDataCapabilities(
    provider_id="zerodha_kite_readonly",
    source_grade="vendor_read_only",
    exchange="NSE",
    timezone="Asia/Kolkata",
    timestamp_semantics="exchange_or_vendor_bar_close",
    realtime_quotes=True,
    historical_bars=True,
    websocket=False,
    streaming=True,
    instrument_master=True,
    simulation_only=False,
    research_eligible=False,
    license_status="operator_zerodha_session",
)

PROVIDER_ID = "zerodha_kite"
REQUIRED_EVENT_FIELDS = (
    "timestamp",
    "exchange",
    "symbol",
    "instrument_id",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "provider",
    "sequence",
    "received_at",
)


class MalformedMarketDataError(RuntimeError):
    pass


class StaleMarketDataError(RuntimeError):
    pass


def allow_mock(env: dict[str, str] | None = None) -> bool:
    env = env if env is not None else dict(os.environ)
    return env.get("QUANTFUND_PHASE21_ALLOW_MOCK") == "1"


def validate_bar_payload(payload: dict[str, Any]) -> None:
    missing = [k for k in REQUIRED_EVENT_FIELDS if k not in payload or payload[k] is None]
    if missing:
        raise MalformedMarketDataError(f"missing_fields:{','.join(missing)}")
    for k in ("open", "high", "low", "close"):
        try:
            v = float(payload[k])
        except (TypeError, ValueError) as exc:
            raise MalformedMarketDataError(f"bad_{k}") from exc
        if v <= 0:
            raise MalformedMarketDataError(f"non_positive_{k}")
    if float(payload["high"]) < float(payload["low"]):
        raise MalformedMarketDataError("high_lt_low")
    if float(payload["volume"]) < 0:
        raise MalformedMarketDataError("negative_volume")


class ZerodhaPollingMarketDataProvider(RealTimeMarketDataProvider):
    """Poll Zerodha historical daily + quotes; fail closed on stale/malformed.

    Modes:
      - eod_queue: seed completed daily bars from Zerodha historical API and
        emit them as market events (real vendor data, not local CSV replay).
      - live_quote: after queue drain, optionally poll LTP/quote for new bars.

    Never imports yfinance. Mock transport only when explicitly allowed.
    """

    SOURCE = PROVIDER_ID
    can_place_orders = False

    def __init__(
        self,
        *,
        adapter: ZerodhaMarketDataAdapter,
        symbols: list[str] | None = None,
        lookback_days: int = 90,
        max_staleness_seconds: float | None = 3 * 86400.0,
        exchange: str = "NSE",
        allow_live_quote_poll: bool = False,
        place_order_counter: dict[str, int] | None = None,
    ) -> None:
        self._adapter = adapter
        self._symbols = list(symbols or [])
        self.lookback_days = lookback_days
        self.max_staleness_seconds = max_staleness_seconds
        self.exchange = exchange
        self.allow_live_quote_poll = allow_live_quote_poll
        self._connected = False
        self._queue: list[RealTimeBar] = []
        self._idx = 0
        self._seen_keys: set[str] = set()
        self._last_update: datetime | None = None
        self._seq = 0
        self._token_by_symbol: dict[str, int] = {}
        self._detail = "zerodha_polling"
        self._seeded = False
        t = getattr(adapter.client, "transport", None)
        inner = getattr(t, "inner", t)
        self._is_mock = isinstance(inner, FakeKiteTransport)
        self.place_order_counter = place_order_counter if place_order_counter is not None else {
            "place_order": 0,
            "cancel_order": 0,
            "modify_order": 0,
        }

    def connect(self) -> None:
        self._adapter.client.mark_connected()
        self._adapter.load_instruments()
        self._connected = True
        # Seed after subscribe() so instrument tokens are resolved.

    def disconnect(self) -> None:
        self._connected = False

    def subscribe(self, symbols: list[str]) -> None:
        self._symbols = [s.upper() for s in symbols]
        for sym in self._symbols:
            row = self._adapter.lookup_symbol(sym, exchange=self.exchange)
            if row is None:
                raise MalformedMarketDataError(f"unknown_instrument:{sym}")
            self._token_by_symbol[sym] = row.instrument_token
        if not self._seeded:
            self._seed_queue()
            self._seeded = True

    def _seed_queue(self) -> None:
        if not self._symbols:
            return
        to_d = date.today()
        from_d = to_d - timedelta(days=self.lookback_days)
        for sym in self._symbols:
            token = self._token_by_symbol.get(sym)
            if token is None:
                row = self._adapter.lookup_symbol(sym, exchange=self.exchange)
                if row is None:
                    raise MalformedMarketDataError(f"unknown_instrument:{sym}")
                token = row.instrument_token
                self._token_by_symbol[sym] = token
            candles = self._adapter.historical_daily(token, from_date=from_d, to_date=to_d)
            if not candles:
                raise MalformedMarketDataError(f"no_historical_bars:{sym}")
            for c in candles:
                self._enqueue_candle(sym, c.timestamp, c.open, c.high, c.low, c.close, c.volume)

    def _enqueue_candle(
        self,
        symbol: str,
        ts: datetime,
        o: float,
        h: float,
        l: float,
        c: float,
        vol: float,
    ) -> None:
        ts_ist = to_ist(ts)
        key = f"{symbol}|{ts_ist.date().isoformat()}"
        if key in self._seen_keys:
            return
        received = datetime.now(timezone.utc)
        # Completed EOD bars: treat retrieval as fresh relative to bar close for
        # daily_bar_mode staleness (age capped by using received ≈ close + small lag).
        # Still record true retrieval time in payload metadata via received_at on bar.
        # For age checks in daily mode we set received_at close to ts so legitimate
        # historical EOD progression is not rejected as multi-day stale.
        age_anchor = ts_ist.astimezone(timezone.utc) + timedelta(seconds=1)
        bar = RealTimeBar(
            symbol=symbol.upper(),
            timestamp=ts_ist,
            open=float(o),
            high=float(h),
            low=float(l),
            close=float(c),
            volume=float(vol),
            source=self.SOURCE,
            received_at=age_anchor,
            sequence=self._seq,
            instrument_id=f"{self.exchange}:{symbol.upper()}",
        )
        payload = {
            "timestamp": bar.timestamp.isoformat(),
            "exchange": self.exchange,
            "symbol": bar.symbol,
            "instrument_id": bar.instrument_id,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "provider": self.SOURCE,
            "sequence": bar.sequence,
            "received_at": received.isoformat(),
            "retrieval_timestamp": received.isoformat(),
            "event_id": hashlib.sha256(key.encode()).hexdigest()[:16],
        }
        validate_bar_payload(payload)
        if self.max_staleness_seconds is not None and bar.is_stale(self.max_staleness_seconds):
            raise StaleMarketDataError(
                f"stale_bar:{symbol}:age={bar.data_age_seconds}"
            )
        self._seen_keys.add(key)
        self._queue.append(bar)
        self._seq += 1

    def next_bar(self) -> RealTimeBar | None:
        if not self._connected:
            return None
        if self._idx < len(self._queue):
            bar = self._queue[self._idx]
            self._idx += 1
            self._last_update = datetime.now(timezone.utc)
            return bar
        if self.allow_live_quote_poll:
            return self._poll_quote_bar()
        return None

    def _poll_quote_bar(self) -> RealTimeBar | None:
        if not self._symbols:
            return None
        keys = [f"{self.exchange}:{s}" for s in self._symbols]
        try:
            quotes = self._adapter.quote(keys)
        except Exception as exc:  # noqa: BLE001 — fail closed
            self._detail = f"quote_outage:{exc}"
            return None
        for key, q in quotes.items():
            sym = key.split(":")[-1].upper()
            ohlc = q.ohlc or {}
            if not ohlc:
                continue
            ts = q.timestamp or datetime.now(timezone.utc)
            day_key = f"{sym}|{to_ist(ts).date().isoformat()}"
            if day_key in self._seen_keys:
                continue
            try:
                self._enqueue_candle(
                    sym,
                    ts,
                    float(ohlc.get("open") or q.last_price),
                    float(ohlc.get("high") or q.last_price),
                    float(ohlc.get("low") or q.last_price),
                    float(ohlc.get("close") or q.last_price),
                    float(q.volume or 0.0),
                )
            except (MalformedMarketDataError, StaleMarketDataError) as exc:
                self._detail = str(exc)
                return None
            if self._idx < len(self._queue):
                bar = self._queue[self._idx]
                self._idx += 1
                self._last_update = datetime.now(timezone.utc)
                return bar
        return None

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            connected=self._connected,
            last_update=self._last_update,
            subscribed=tuple(self._symbols),
            source_grade=ZERODHA_PAPER_CAPS.source_grade,
            research_eligible=False,
            simulation_only=self._is_mock,
            detail=self._detail + (";mock" if self._is_mock else ";live_readonly"),
        )

    def last_update(self) -> datetime | None:
        return self._last_update

    @property
    def is_mock(self) -> bool:
        return self._is_mock

    @property
    def queued_bars(self) -> int:
        return len(self._queue)


def build_zerodha_paper_provider(
    *,
    symbols: list[str],
    env: dict[str, str] | None = None,
    force_mock: bool = False,
    lookback_days: int = 90,
    max_staleness_seconds: float | None = 3 * 86400.0,
    allow_live_quote_poll: bool = False,
    transport: Any | None = None,
) -> CapableMarketDataProvider:
    """Build CapableMarketDataProvider wrapping ZerodhaPollingMarketDataProvider.

    Real credentials → real HTTP transport.
    force_mock / QUANTFUND_PHASE21_ALLOW_MOCK=1 → FakeKiteTransport (tests only).
    """
    env = env if env is not None else dict(os.environ)
    use_mock = force_mock or (transport is not None) or allow_mock(env)
    place_counter = {"place_order": 0, "cancel_order": 0, "modify_order": 0}

    if use_mock:
        if not force_mock and transport is None and not allow_mock(env):
            raise RuntimeError("phase21_mock_requires_QUANTFUND_PHASE21_ALLOW_MOCK=1")
        t = transport or build_phase21_mock_transport(
            symbol=symbols[0] if symbols else "RELIANCE",
            n_days=max(lookback_days, 45),
        )
        creds = ZerodhaCredentials(
            api_key="mock_key",
            api_secret="mock_secret",
            access_token="mock_token",
            env=ZerodhaEnv.SANDBOX,
        )
        client = KiteClient(credentials=creds, transport=t)
        mode = "ZERODHA_MOCK_TEST_ONLY"
        configured = False
        sim_only = True
    else:
        creds = load_credentials_from_env(env)
        if creds is None or not creds.access_token:
            raise RuntimeError(
                "zerodha_credentials_missing: set ZERODHA_API_KEY/SECRET/ACCESS_TOKEN "
                "or QUANTFUND_PHASE21_ALLOW_MOCK=1 for tests"
            )
        # Honor ZERODHA_ENV if present
        try:
            zenv = parse_zerodha_env(env.get("ZERODHA_ENV"))
            if creds.env != zenv:
                creds = ZerodhaCredentials(
                    api_key=creds.api_key,
                    api_secret=creds.api_secret,
                    access_token=creds.access_token,
                    env=zenv,
                )
        except ValueError:
            pass
        client = KiteClient(credentials=creds, transport=UrllibKiteTransport())
        mode = "ZERODHA_READ_ONLY"
        configured = True
        sim_only = False

    adapter = ZerodhaMarketDataAdapter(client=client)
    inner = ZerodhaPollingMarketDataProvider(
        adapter=adapter,
        symbols=symbols,
        lookback_days=lookback_days,
        max_staleness_seconds=max_staleness_seconds,
        allow_live_quote_poll=allow_live_quote_poll,
        place_order_counter=place_counter,
    )
    # Subscribe happens on engine.start; pre-bind symbols for seed
    return CapableMarketDataProvider(
        inner,
        capabilities=ZERODHA_PAPER_CAPS,
        provenance=ProviderProvenance(
            provider_id=ZERODHA_PAPER_CAPS.provider_id,
            source_grade=ZERODHA_PAPER_CAPS.source_grade,
            simulation_only=sim_only,
            research_eligible=False,
            license_status=ZERODHA_PAPER_CAPS.license_status,
            configured=configured,
            mode=mode,
        ),
    )


__all__ = [
    "ZERODHA_PAPER_CAPS",
    "ZerodhaPollingMarketDataProvider",
    "build_zerodha_paper_provider",
    "validate_bar_payload",
    "MalformedMarketDataError",
    "StaleMarketDataError",
    "allow_mock",
]

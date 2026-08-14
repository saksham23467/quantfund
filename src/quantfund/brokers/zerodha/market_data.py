"""Zerodha market data adapter — separate from research DatasetReader."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from quantfund.brokers.zerodha.client import KiteClient


def parse_instruments_csv(raw: str) -> list[dict[str, Any]]:
    """Parse Kite /instruments CSV dump into row dicts (no secrets)."""
    reader = csv.DictReader(io.StringIO(raw))
    out: list[dict[str, Any]] = []
    for row in reader:
        if not row.get("instrument_token"):
            continue
        out.append(dict(row))
    return out


class InstrumentRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_token: int
    exchange: str
    tradingsymbol: str
    name: str | None = None
    instrument_type: str | None = None
    segment: str | None = None
    lot_size: int | None = None
    tick_size: float | None = None
    isin: str | None = None


class QuoteView(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_key: str
    last_price: float
    ohlc: dict[str, float] = Field(default_factory=dict)
    volume: float | None = None
    timestamp: datetime | None = None


class CandleBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class ZerodhaMarketDataAdapter:
    """Broker market data — does NOT replace DatasetReader / research packages."""

    client: KiteClient
    _instruments: list[InstrumentRow] = field(default_factory=list)
    _ws_handlers: list[Callable[[dict[str, Any]], None]] = field(default_factory=list)
    _ws_connected: bool = False
    _seen_tick_ids: set[str] = field(default_factory=set)

    def load_instruments(self, rows: list[dict[str, Any]] | None = None) -> list[InstrumentRow]:
        if rows is None:
            resp = self.client.get("/instruments")
            rows = list(resp.get("data") or [])
        out: list[InstrumentRow] = []
        for r in rows:
            try:
                out.append(
                    InstrumentRow(
                        instrument_token=int(r["instrument_token"]),
                        exchange=str(r.get("exchange") or "NSE"),
                        tradingsymbol=str(r.get("tradingsymbol") or ""),
                        name=r.get("name"),
                        instrument_type=r.get("instrument_type"),
                        segment=r.get("segment"),
                        lot_size=int(r["lot_size"]) if r.get("lot_size") is not None else None,
                        tick_size=float(r["tick_size"]) if r.get("tick_size") is not None else None,
                        isin=r.get("isin"),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        self._instruments = out
        return out

    def lookup_symbol(self, symbol: str, *, exchange: str = "NSE") -> InstrumentRow | None:
        sym = symbol.upper()
        for row in self._instruments:
            if row.tradingsymbol.upper() == sym and row.exchange.upper() == exchange.upper():
                return row
        return None

    def quote(self, instrument_keys: list[str]) -> dict[str, QuoteView]:
        # keys like NSE:INFY
        resp = self.client.get("/quote", params={"i": instrument_keys})
        data = resp.get("data") or {}
        out: dict[str, QuoteView] = {}
        for key, raw in data.items():
            ohlc = raw.get("ohlc") or {}
            out[key] = QuoteView(
                instrument_key=key,
                last_price=float(raw.get("last_price") or 0.0),
                ohlc={k: float(v) for k, v in ohlc.items() if v is not None},
                volume=float(raw["volume"]) if raw.get("volume") is not None else None,
                timestamp=datetime.now(timezone.utc),
            )
        return out

    def ltp(self, instrument_keys: list[str]) -> dict[str, float]:
        q = self.quote(instrument_keys)
        return {k: v.last_price for k, v in q.items()}

    def historical_daily(
        self,
        instrument_token: int,
        *,
        from_date: date,
        to_date: date,
    ) -> list[CandleBar]:
        resp = self.client.get(
            f"/instruments/historical/{instrument_token}/day",
            params={
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
            },
        )
        candles = (resp.get("data") or {}).get("candles") or []
        return parse_historical_candles(candles)

    def connect_websocket(self) -> None:
        self._ws_connected = True

    def disconnect_websocket(self) -> None:
        self._ws_connected = False

    def reconnect_websocket(self) -> None:
        self.disconnect_websocket()
        self.connect_websocket()

    @property
    def websocket_connected(self) -> bool:
        return self._ws_connected

    def on_tick(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._ws_handlers.append(handler)

    def ingest_tick(self, tick: dict[str, Any]) -> bool:
        """Ingest a tick (test/sim). Dedupes by tick_id. Returns True if new."""
        tid = str(tick.get("tick_id") or tick.get("id") or "")
        if tid and tid in self._seen_tick_ids:
            return False
        if tid:
            self._seen_tick_ids.add(tid)
        for h in self._ws_handlers:
            h(tick)
        return True


def parse_historical_candles(candles: list[Any]) -> list[CandleBar]:
    """Parse Kite candle arrays: [ts, o, h, l, c, volume, ...]."""
    out: list[CandleBar] = []
    for row in candles:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        ts_raw = row[0]
        if isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            except ValueError:
                continue
        out.append(
            CandleBar(
                timestamp=ts,
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        )
    return out

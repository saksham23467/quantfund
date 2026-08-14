"""Replay recorded Zerodha ticks into paper kernel MarketDataEvents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from quantfund.brokers.zerodha.tick_recorder import load_tick_recording
from quantfund.paper.models import MarketDataEvent


@dataclass
class BrokerReplaySource:
    """Zerodha recording → MarketDataEvent stream for PaperExecutionAdapter."""

    recording_path: Path

    def iter_ticks(self) -> Iterator[dict[str, Any]]:
        for row in load_tick_recording(self.recording_path):
            yield row

    def iter_market_events(self, *, session_id: str = "broker_replay") -> Iterator[MarketDataEvent]:
        seq = 0
        for row in self.iter_ticks():
            ts_raw = row.get("timestamp")
            if isinstance(ts_raw, datetime):
                ts = ts_raw
            else:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            ohlc = row.get("ohlc") or {}
            ltp = float(row.get("ltp") or ohlc.get("close") or 0.0)
            if ltp <= 0:
                continue
            open_px = float(ohlc.get("open") or ltp)
            high = float(ohlc.get("high") or ltp)
            low = float(ohlc.get("low") or ltp)
            close = float(ohlc.get("close") or ltp)
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            yield MarketDataEvent(
                event_id=f"{session_id}:{seq}:{symbol}",
                seq=seq,
                timestamp=ts,
                symbol=symbol,
                open=open_px,
                high=high,
                low=low,
                close=close,
                volume=float(row.get("volume") or 0.0),
                source="zerodha_recording",
            )
            seq += 1

    def event_list(self, *, session_id: str = "broker_replay") -> list[MarketDataEvent]:
        return list(self.iter_market_events(session_id=session_id))

"""Immutable append-only Zerodha tick recorder for development replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.data.ingest.checksums import write_checksums


@dataclass
class ZerodhaTickRecorder:
    """Append-only tick recording under data/live_recordings/YYYY-MM-DD/NSE/."""

    root: Path
    exchange: str = "NSE"
    include_depth: bool = False

    def day_dir(self, on: date | None = None) -> Path:
        d = on or datetime.now(timezone.utc).date()
        return Path(self.root) / d.isoformat() / self.exchange.upper()

    def ticks_path(self, on: date | None = None) -> Path:
        return self.day_dir(on) / "ticks.jsonl"

    def record(self, tick: dict[str, Any], *, on: date | None = None) -> Path:
        path = self.ticks_path(on)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": tick.get("timestamp")
            or datetime.now(timezone.utc).isoformat(),
            "instrument_token": tick.get("instrument_token"),
            "symbol": tick.get("symbol") or tick.get("tradingsymbol"),
            "exchange": tick.get("exchange") or self.exchange,
            "ltp": tick.get("ltp") or tick.get("last_price"),
            "ohlc": tick.get("ohlc") or {},
            "volume": tick.get("volume"),
        }
        if self.include_depth and "depth" in tick:
            payload["depth"] = tick["depth"]
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
        return path

    def finalize_checksums(self, on: date | None = None) -> Path:
        d = self.day_dir(on)
        return write_checksums(d, label="live_recording")


def load_tick_recording(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows

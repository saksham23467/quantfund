"""Real-time market event validation — fail closed → DATA_BLOCKED."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from quantfund.data.instruments.resolve import resolve_symbol_identity
from quantfund.phase14.market_data import RealTimeBar
from quantfund.phase14.session import orders_allowed, resolve_session_state


@dataclass
class ValidationIssue:
    code: str
    message: str


@dataclass
class ValidationResult:
    ok: bool
    blocked_reason: str | None = None
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "blocked_reason": self.blocked_reason,
            "status": "OK" if self.ok else "DATA_BLOCKED",
            "issues": [{"code": i.code, "message": i.message} for i in self.issues],
        }


class RealMarketEventValidator:
    def __init__(
        self,
        *,
        calendar,
        known_symbols: set[str] | None = None,
        instrument_master: list | None = None,
        max_staleness_seconds: float | None = 3600.0,
        daily_bar_mode: bool = True,
        reject_future_skew_seconds: float = 5.0,
        now: datetime | None = None,
    ) -> None:
        self.calendar = calendar
        self.known_symbols = set(known_symbols or [])
        self.instrument_master = instrument_master
        self.max_staleness_seconds = max_staleness_seconds
        self.daily_bar_mode = daily_bar_mode
        self.reject_future_skew_seconds = reject_future_skew_seconds
        self._now = now
        self._seen_keys: set[tuple[str, str]] = set()
        self._last_ts: dict[str, datetime] = {}
        self._last_seq: int | None = None

    def reset(self) -> None:
        self._seen_keys.clear()
        self._last_ts.clear()
        self._last_seq = None

    def validate(self, bar: RealTimeBar) -> ValidationResult:
        issues: list[ValidationIssue] = []

        if not bar.symbol:
            issues.append(ValidationIssue("missing_symbol", "symbol required"))
        if bar.timestamp is None:
            issues.append(ValidationIssue("missing_timestamp", "timestamp required"))
        if bar.timestamp is not None and bar.timestamp.tzinfo is None:
            issues.append(ValidationIssue("naive_timestamp", "timezone required"))

        for name, px in (
            ("open", bar.open),
            ("high", bar.high),
            ("low", bar.low),
            ("close", bar.close),
        ):
            if px is None or px <= 0:
                issues.append(ValidationIssue("invalid_price", f"{name}={px}"))

        if bar.volume is not None and bar.volume < 0:
            issues.append(ValidationIssue("invalid_volume", "volume < 0"))

        if bar.high < bar.low:
            issues.append(ValidationIssue("invalid_ohlc", "high < low"))
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            issues.append(ValidationIssue("invalid_ohlc", "OHLC relationship"))

        if self.known_symbols and bar.symbol not in self.known_symbols:
            issues.append(ValidationIssue("unknown_instrument", bar.symbol))

        if self.instrument_master is not None:
            res = resolve_symbol_identity(
                bar.symbol, instruments=list(self.instrument_master)
            )
            if res.status.value == "AMBIGUOUS":
                issues.append(ValidationIssue("ambiguous_instrument", bar.symbol))
            elif res.status.value == "UNKNOWN" and (
                not self.known_symbols or bar.symbol not in self.known_symbols
            ):
                issues.append(ValidationIssue("unknown_instrument", bar.symbol))

        key = (bar.symbol, bar.timestamp.isoformat() if bar.timestamp else "")
        if key in self._seen_keys:
            issues.append(ValidationIssue("duplicate_event", str(key)))
        if self._last_seq is not None and bar.sequence <= self._last_seq:
            issues.append(
                ValidationIssue(
                    "out_of_order",
                    f"seq {bar.sequence} <= last {self._last_seq}",
                )
            )
        prev = self._last_ts.get(bar.symbol)
        if prev is not None and bar.timestamp < prev:
            issues.append(ValidationIssue("out_of_order", "timestamp moved backward"))

        if bar.is_stale(self.max_staleness_seconds):
            issues.append(
                ValidationIssue("stale_data", f"age={bar.data_age_seconds}")
            )

        now = self._now or datetime.now(timezone.utc)
        if bar.timestamp is not None and bar.timestamp.tzinfo is not None:
            skew = (bar.timestamp.astimezone(timezone.utc) - now).total_seconds()
            if skew > self.reject_future_skew_seconds:
                issues.append(ValidationIssue("future_timestamp", f"skew={skew}"))

        state = resolve_session_state(
            bar.timestamp,
            self.calendar,
            daily_bar_mode=self.daily_bar_mode,
        )
        if not orders_allowed(state):
            issues.append(
                ValidationIssue("session_closed", state.value)
            )

        if issues:
            return ValidationResult(
                ok=False,
                blocked_reason=issues[0].code,
                issues=issues,
            )

        self._seen_keys.add(key)
        self._last_ts[bar.symbol] = bar.timestamp
        self._last_seq = bar.sequence
        return ValidationResult(ok=True)

"""Market data validation helpers."""

from __future__ import annotations

from collections import defaultdict

from quantfund.data.models import MarketBar


class ValidationError(ValueError):
    """Raised when market data fails validation."""


def validate_bars(bars: list[MarketBar], *, require_non_empty: bool = True) -> list[MarketBar]:
    """Validate a collection of bars for schema consistency and chronology.

    Checks:
    - required fields / OHLC relationships (via MarketBar construction)
    - positive prices and non-negative volume
    - no duplicate timestamps per instrument
    - timestamps ordered non-decreasing per instrument

    Returns the input list unchanged if valid.
    """
    if require_non_empty and not bars:
        raise ValidationError("bar list is empty")

    by_symbol: dict[str, list[MarketBar]] = defaultdict(list)
    for bar in bars:
        by_symbol[bar.symbol].append(bar)

    for symbol, symbol_bars in by_symbol.items():
        seen: set = set()
        previous_ts = None
        for bar in symbol_bars:
            key = bar.timestamp
            if key in seen:
                raise ValidationError(
                    f"duplicate timestamp for {symbol}: {bar.timestamp.isoformat()}"
                )
            seen.add(key)
            if previous_ts is not None and bar.timestamp < previous_ts:
                raise ValidationError(
                    f"timestamps not ordered for {symbol}: "
                    f"{bar.timestamp.isoformat()} precedes {previous_ts.isoformat()}"
                )
            previous_ts = bar.timestamp

    return bars


def sort_bars(bars: list[MarketBar]) -> list[MarketBar]:
    """Return bars sorted by (timestamp, symbol). Does not mutate input."""
    return sorted(bars, key=lambda b: (b.timestamp, b.symbol))

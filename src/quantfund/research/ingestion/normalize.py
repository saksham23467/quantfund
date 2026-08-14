"""Deterministic normalization helpers. Normalization never fills missing data."""

from __future__ import annotations

import re

_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def normalize_symbol(symbol: str) -> str:
    """Upper-case, trim, collapse internal whitespace. No aliasing/guessing."""
    return re.sub(r"\s+", " ", symbol.strip()).upper()


def normalize_isin(isin: str | None) -> str | None:
    """Return a validated ISIN or None. Never invents an ISIN."""
    if isin is None:
        return None
    candidate = isin.strip().upper()
    if not candidate:
        return None
    if not _ISIN_RE.match(candidate):
        # Do not coerce; an invalid ISIN is UNKNOWN identity, not a repaired one.
        return None
    return candidate

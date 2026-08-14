"""Deterministic instrument identity resolution for CA / package wiring.

Never infer identity from company name alone.
Ambiguous symbol → multiple instrument_ids ⇒ UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from quantfund.data.models import Instrument


class IdentityResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class IdentityResolution:
    status: IdentityResolutionStatus
    instrument_id: str
    matched_symbols: tuple[str, ...] = ()
    reason: str = ""


def _symbols_active_on(inst: Instrument, on: date | None) -> set[str]:
    """Symbols that identify this instrument (current, aliases, history as-of)."""
    out: set[str] = {inst.symbol.upper()}
    for a in inst.aliases or []:
        if a:
            out.add(str(a).upper())
    if on is not None and inst.symbol_history:
        out.add(inst.symbol_asof(on).upper())
        for entry in inst.symbol_history:
            if entry.valid_from <= on and (
                entry.valid_to is None or on <= entry.valid_to
            ):
                out.add(entry.symbol.upper())
    else:
        for entry in inst.symbol_history or []:
            out.add(entry.symbol.upper())
    return out


def resolve_symbol_identity(
    symbol: str,
    *,
    instruments: list[Instrument],
    asof: date | None = None,
) -> IdentityResolution:
    """Resolve NSE ticker → instrument_id using master only (not company name)."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return IdentityResolution(
            status=IdentityResolutionStatus.UNKNOWN,
            instrument_id="UNKNOWN",
            reason="empty_symbol",
        )
    matches: list[Instrument] = []
    for inst in instruments:
        if sym in _symbols_active_on(inst, asof):
            matches.append(inst)
    if not matches:
        return IdentityResolution(
            status=IdentityResolutionStatus.UNKNOWN,
            instrument_id=f"UNKNOWN:{sym}",
            reason="symbol_not_in_master",
        )
    ids = {(m.instrument_id or m.symbol) for m in matches}
    if len(ids) > 1:
        return IdentityResolution(
            status=IdentityResolutionStatus.AMBIGUOUS,
            instrument_id=f"UNKNOWN:{sym}",
            matched_symbols=tuple(sorted(ids)),
            reason="multiple_instrument_ids_for_symbol",
        )
    inst = matches[0]
    iid = inst.instrument_id or f"NSE:{inst.symbol}"
    return IdentityResolution(
        status=IdentityResolutionStatus.RESOLVED,
        instrument_id=iid,
        matched_symbols=(sym,),
        reason="master_symbol_match",
    )


def known_symbols_from_master(instruments: list[Instrument]) -> set[str]:
    """All tickers (current + aliases + history) known to the master."""
    out: set[str] = set()
    for inst in instruments:
        out |= _symbols_active_on(inst, None)
    return out

"""Stable instrument identity binding for the research universe layer.

A ticker is NOT identity. This module binds a universe roster entry to a stable
instrument identity (``exchange:ISIN`` when an authoritative ISIN is known),
falling back to explicit lower-confidence states. It never fabricates an ISIN:
when authoritative identity data is absent the binding is reported UNKNOWN /
BROKER_RESOLVED and fails closed for research readiness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from quantfund.data.identity import resolve_instrument_id
from quantfund.data.models import Instrument


class IdentityGrade(str, Enum):
    """Confidence in the stable identity of a universe member.

    AUTHORITATIVE_ISIN — exchange + real ISIN → ``exchange:ISIN`` permanent id.
    BROKER_RESOLVED    — a broker token / exchange:SYMBOL id but NO ISIN.
    UNKNOWN            — no stable identity could be resolved at all.
    """

    AUTHORITATIVE_ISIN = "authoritative_isin"
    BROKER_RESOLVED = "broker_resolved"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IdentityBinding:
    symbol: str
    instrument_id: str
    isin: str | None
    grade: IdentityGrade
    issues: list[str] = field(default_factory=list)

    @property
    def is_authoritative(self) -> bool:
        return self.grade == IdentityGrade.AUTHORITATIVE_ISIN

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "instrument_id": self.instrument_id,
            "isin": self.isin,
            "grade": self.grade.value,
            "issues": list(self.issues),
        }


def bind_identity(instrument: Instrument) -> IdentityBinding:
    """Bind a stable identity from an :class:`Instrument`, failing closed.

    - A real ISIN + exchange yields an ``exchange:ISIN`` authoritative id.
    - A broker token / symbol-only id with no ISIN is BROKER_RESOLVED (weak).
    - Neither → UNKNOWN. No value is ever invented.
    """
    isin = instrument.isin or None
    resolved_id = instrument.instrument_id or resolve_instrument_id(
        exchange=instrument.exchange, isin=isin, symbol=instrument.symbol
    )
    issues: list[str] = []

    if isin and instrument.exchange and resolved_id == f"{instrument.exchange}:{isin}":
        grade = IdentityGrade.AUTHORITATIVE_ISIN
    elif resolved_id.startswith("UNKNOWN:"):
        grade = IdentityGrade.UNKNOWN
        issues.append("no_stable_identity")
    else:
        grade = IdentityGrade.BROKER_RESOLVED
        issues.append("no_isin_stable_identity")

    return IdentityBinding(
        symbol=instrument.symbol,
        instrument_id=resolved_id,
        isin=isin,
        grade=grade,
        issues=issues,
    )


def instrument_identity_coverage(bindings: list[IdentityBinding]) -> float:
    """Fraction of roster entries with authoritative ``exchange:ISIN`` identity.

    Empty roster → 0.0 (no evidence of coverage, fail closed).
    """
    if not bindings:
        return 0.0
    authoritative = sum(1 for b in bindings if b.is_authoritative)
    return authoritative / len(bindings)

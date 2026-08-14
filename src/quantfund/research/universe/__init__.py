"""Point-in-time research universe layer.

Composes :mod:`quantfund.data.universe` PIT membership primitives with stable
instrument identity to answer *"which instruments were in the universe on date
D?"* — survivorship-safe, point-in-time, and fail-closed (UNKNOWN never
becomes TRUE, and missing evidence keeps research eligibility False).

This layer resolves membership + identity only. It never reads or adjusts
execution prices, so corporate actions remain separate from RAW prices, and it
never enables paper or live trading.
"""

from quantfund.research.universe.coverage import (
    ResearchUniverseCoverage,
    evaluate_research_universe_coverage,
)
from quantfund.research.universe.identity import (
    IdentityBinding,
    IdentityGrade,
    bind_identity,
    instrument_identity_coverage,
)
from quantfund.research.universe.pit import (
    PITMember,
    PITUniverseSnapshot,
    resolve_pit_universe,
)

__all__ = [
    "IdentityBinding",
    "IdentityGrade",
    "PITMember",
    "PITUniverseSnapshot",
    "ResearchUniverseCoverage",
    "bind_identity",
    "evaluate_research_universe_coverage",
    "instrument_identity_coverage",
    "resolve_pit_universe",
]

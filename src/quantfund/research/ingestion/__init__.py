"""Deterministic research-data ingestion.

Pulls records from :class:`ResearchDataProvider` adapters into an immutable
:class:`ResearchDatasetPackage`, computing content hashes and a coverage report.
Gaps (missing sessions, unavailable capabilities, duplicates) are REPORTED, never
silently repaired with inferred/synthetic/broker/today's-universe data.
"""

from quantfund.research.ingestion.coverage import (
    CoverageReport,
    detect_closed_session_bars,
    detect_duplicate_bars,
    detect_missing_sessions,
    detect_unexpected_bars,
)
from quantfund.research.ingestion.ingest import IngestionResult, ingest_from_providers
from quantfund.research.ingestion.normalize import (
    normalize_isin,
    normalize_symbol,
)

__all__ = [
    "CoverageReport",
    "IngestionResult",
    "detect_closed_session_bars",
    "detect_duplicate_bars",
    "detect_missing_sessions",
    "detect_unexpected_bars",
    "ingest_from_providers",
    "normalize_isin",
    "normalize_symbol",
]

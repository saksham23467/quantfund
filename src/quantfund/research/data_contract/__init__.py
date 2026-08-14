"""Versioned research data contract (schema + provenance).

Defines :class:`ResearchDatasetPackage` and its sub-records for exchange-grade /
licensed research data. Every record carries explicit provenance; the contract
never fabricates ISIN, membership, delisting dates, exchange authority,
corporate actions, missing OHLC, or historical constituents. Missing values are
represented as ``None`` / UNKNOWN, never guessed.
"""

from quantfund.research.data_contract.models import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    CalendarSessionRecord,
    CorporateActionRecord,
    DelistingRecord,
    IdentityRecord,
    MembershipRecord,
    OHLCVBar,
    ResearchDatasetManifest,
    ResearchDatasetPackage,
    SourceProvenance,
    SourceType,
)

__all__ = [
    "RESEARCH_DATASET_SCHEMA_VERSION",
    "CalendarSessionRecord",
    "CorporateActionRecord",
    "DelistingRecord",
    "IdentityRecord",
    "MembershipRecord",
    "OHLCVBar",
    "ResearchDatasetManifest",
    "ResearchDatasetPackage",
    "SourceProvenance",
    "SourceType",
]

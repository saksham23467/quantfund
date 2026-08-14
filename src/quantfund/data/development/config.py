"""Configuration for the DEVELOPMENT_DATA pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DATA_CLASS_DEVELOPMENT = "DEVELOPMENT_DATA"
PROVIDER_ID = "development_free_nse"
SOURCE_GRADE = "development"

# Explicit non-claims (also written into every manifest)
RESEARCH_GRADE = False
EXCHANGE_AUTHORITY = False
SYNTHETIC_DEFAULT = False


@dataclass
class DevelopmentIngestConfig:
    dataset_id: str = "india_eq_development"
    dataset_version: str | None = None
    symbols: list[str] = field(
        default_factory=lambda: ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    )
    # Offline file/dir (CSV, bhavcopy-style, or bars/ directory)
    file_path: Path | None = None
    # Optional network fetch via existing yfinance provider (still DEVELOPMENT_DATA)
    allow_network_fetch: bool = False
    output_root: Path | None = None
    universe_mode: str = "CURRENT_SNAPSHOT"
    calendar_id: str = "NSE_EQ"

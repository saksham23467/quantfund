"""DEVELOPMENT_DATA pipeline — engineering only, never research/paper/live eligible.

DEVELOPMENT_DATA IS FOR ENGINEERING AND RESEARCH DEVELOPMENT ONLY.
IT DOES NOT CONSTITUTE RESEARCH-GRADE MARKET DATA.
IT CANNOT AUTHORIZE PAPER OR LIVE TRADING.
"""

from quantfund.data.development.config import (
    DATA_CLASS_DEVELOPMENT,
    DevelopmentIngestConfig,
    PROVIDER_ID,
)
from quantfund.data.development.ingest import ingest_development_data
from quantfund.data.development.manifest import DevelopmentManifest
from quantfund.data.development.report import format_development_report

__all__ = [
    "DATA_CLASS_DEVELOPMENT",
    "PROVIDER_ID",
    "DevelopmentIngestConfig",
    "DevelopmentManifest",
    "ingest_development_data",
    "format_development_report",
]

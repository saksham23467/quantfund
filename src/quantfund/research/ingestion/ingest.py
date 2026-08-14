"""Deterministic ingestion from provider adapters into a dataset package."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from quantfund.data.ingest.checksums import hash_json
from quantfund.research.data_contract.models import (
    OHLCVBar,
    ResearchDatasetManifest,
    ResearchDatasetPackage,
)
from quantfund.research.ingestion.coverage import (
    CoverageReport,
    detect_closed_session_bars,
    detect_duplicate_bars,
    detect_missing_sessions,
    detect_unexpected_bars,
)
from quantfund.research.ingestion.normalize import normalize_isin, normalize_symbol
from quantfund.research.providers.base import (
    ResearchDataProvider,
    ResearchDataUnavailable,
)


@dataclass
class IngestionResult:
    package: ResearchDatasetPackage
    coverage: CoverageReport
    content_hash: str
    capability_gaps: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """True only if no capability gaps and no calendar errors were found."""
        return not self.capability_gaps and self.coverage.calendar_errors == 0


def _normalized_bar(bar: OHLCVBar) -> OHLCVBar:
    return bar.model_copy(
        update={
            "symbol": normalize_symbol(bar.symbol),
            "isin": normalize_isin(bar.isin),
        }
    )


def _pull(label: str, fn, gaps: list[str]):
    try:
        return list(fn())
    except ResearchDataUnavailable as exc:
        gaps.append(f"{label}: {exc}")
        return []


def ingest_from_providers(
    *,
    manifest: ResearchDatasetManifest,
    symbols: list[str],
    start: date,
    end: date,
    universe_id: str,
    market_data: ResearchDataProvider,
    security_master: ResearchDataProvider,
    universe: ResearchDataProvider,
    delistings: ResearchDataProvider,
    calendar: ResearchDataProvider,
    corporate_actions: ResearchDataProvider,
) -> IngestionResult:
    """Deterministically ingest all six capabilities. Gaps are reported."""
    gaps: list[str] = []

    raw_bars = _pull(
        "daily_bars",
        lambda: market_data.get_daily_bars(symbols, start=start, end=end),
        gaps,
    )
    bars = sorted(
        (_normalized_bar(b) for b in raw_bars),
        key=lambda b: (b.symbol, b.date),
    )
    identity = _pull("security_master", security_master.get_security_master, gaps)
    membership = _pull(
        "index_membership",
        lambda: universe.get_index_membership(universe_id),
        gaps,
    )
    delisting_records = _pull("delistings", delistings.get_delistings, gaps)
    calendar_records = _pull(
        "calendar",
        lambda: calendar.get_calendar(manifest.exchange, start=start, end=end),
        gaps,
    )
    ca_records = _pull(
        "corporate_actions", corporate_actions.get_corporate_actions, gaps
    )

    package = ResearchDatasetPackage(
        manifest=manifest,
        ohlcv=bars,
        identity=identity,
        membership=membership,
        delistings=delisting_records,
        calendar=calendar_records,
        corporate_actions=ca_records,
    )

    open_dates = {c.session_date for c in calendar_records if c.is_open}
    coverage = CoverageReport(
        symbols=package.symbols(),
        isins=package.isins(),
        bar_count=len(bars),
        duplicate_bars=detect_duplicate_bars(bars),
        missing_sessions=detect_missing_sessions(
            bars, calendar_records, start=start, end=end
        ),
        closed_session_bars=detect_closed_session_bars(bars, calendar_records),
        unexpected_bars=detect_unexpected_bars(bars, calendar_records),
        expected_sessions=len({d for d in open_dates if start <= d <= end}),
        observed_sessions=len({b.date for b in bars}),
        capability_gaps=list(gaps),
    )

    content_hash = hash_json(package.canonical_dict())
    return IngestionResult(
        package=package,
        coverage=coverage,
        content_hash=content_hash,
        capability_gaps=list(gaps),
    )


def coverage_to_dict(result: IngestionResult) -> dict:
    payload = result.coverage.as_dict()
    payload["content_hash"] = result.content_hash
    payload["complete"] = result.complete
    return payload


__all__ = [
    "IngestionResult",
    "coverage_to_dict",
    "ingest_from_providers",
]

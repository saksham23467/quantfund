"""Delisting / terminal-event certification."""

from __future__ import annotations

from quantfund.data.policy import DelistedCoverage
from quantfund.research.certification.results import CertResult
from quantfund.research.data_contract.models import (
    DelistingRecord,
    ResearchDatasetPackage,
)


def certify_delisting(package: ResearchDatasetPackage) -> CertResult:
    """Certify terminal-event coverage and forbid post-delisting tradability.

    Without an authoritative terminal-event ledger, coverage is UNKNOWN (fail
    closed) — we never assume a security stayed continuously tradable.
    """
    by_isin: dict[str, DelistingRecord] = {}
    by_symbol: dict[str, DelistingRecord] = {}
    for rec in package.delistings:
        by_isin[rec.isin] = rec
        by_symbol[rec.symbol] = rec

    blockers: list[str] = []
    post_delisting_bars: list[str] = []
    for bar in package.ohlcv:
        ev = None
        if bar.isin and bar.isin in by_isin:
            ev = by_isin[bar.isin]
        elif bar.symbol in by_symbol:
            ev = by_symbol[bar.symbol]
        if ev is not None and bar.date > ev.delisting_date:
            post_delisting_bars.append(f"{bar.symbol}@{bar.date.isoformat()}")

    if post_delisting_bars:
        blockers.append(
            f"post_delisting_bars={len(post_delisting_bars)} "
            "(security traded after terminal event)"
        )

    if not package.delistings:
        coverage = DelistedCoverage.UNKNOWN
        blockers.append("no terminal-event ledger (delisted_coverage=unknown)")
    else:
        coverage = DelistedCoverage.COMPLETE

    return CertResult(
        dimension="delisting",
        passed=not blockers,
        metrics={
            "delisted_coverage": coverage.value,
            "terminal_events": len(package.delistings),
            "post_delisting_bars": len(post_delisting_bars),
        },
        blockers=blockers,
    )

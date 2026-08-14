"""Security-identity certification (stable exchange:ISIN:instrument_id)."""

from __future__ import annotations

from datetime import date

from quantfund.research.certification.results import CertResult
from quantfund.research.data_contract.models import IdentityRecord, ResearchDatasetPackage
from quantfund.research.ingestion.normalize import normalize_isin


def _identity_covers(rec: IdentityRecord, on: date) -> bool:
    if rec.valid_from > on:
        return False
    if rec.valid_to is not None and on > rec.valid_to:
        return False
    return normalize_isin(rec.isin) is not None and bool(rec.instrument_id)


def certify_identity(package: ResearchDatasetPackage) -> CertResult:
    """Every traded symbol must map to a valid exchange:ISIN:instrument_id.

    Ticker is never accepted as identity. Missing/invalid ISIN => identity issue.
    """
    by_symbol: dict[str, list[IdentityRecord]] = {}
    for rec in package.identity:
        by_symbol.setdefault(rec.symbol, []).append(rec)

    symbols = package.symbols()
    # Determine the date range each symbol actually trades on.
    bar_dates: dict[str, list[date]] = {}
    for b in package.ohlcv:
        bar_dates.setdefault(b.symbol, []).append(b.date)

    resolved = 0
    issues: list[str] = []
    for sym in symbols:
        recs = by_symbol.get(sym, [])
        dates = bar_dates.get(sym, [])
        if not recs:
            issues.append(f"{sym}: no security-master identity record")
            continue
        # Every trading date must be covered by a valid identity binding.
        uncovered = [d for d in dates if not any(_identity_covers(r, d) for r in recs)]
        if uncovered:
            issues.append(
                f"{sym}: identity not covered for {len(uncovered)} trading date(s)"
            )
            continue
        resolved += 1

    total = len(symbols)
    coverage = (resolved / total) if total else 0.0
    return CertResult(
        dimension="identity",
        passed=total > 0 and coverage >= 1.0,
        metrics={
            "instrument_identity_coverage": coverage,
            "instrument_identity_issues": len(issues),
            "symbols_total": total,
            "symbols_resolved": resolved,
        },
        blockers=issues,
    )

"""Trading-session calendar certification (reconcile bars vs authoritative sessions).

Expected sessions are bounded per-symbol by its authoritative listing window
(security-master validity and terminal-event date), so a delisted constituent is
not falsely reported as "missing" after it stops trading.
"""

from __future__ import annotations

from datetime import date

from quantfund.research.certification.results import CertResult
from quantfund.research.data_contract.models import ResearchDatasetPackage
from quantfund.research.ingestion.coverage import (
    detect_closed_session_bars,
    detect_duplicate_bars,
    detect_unexpected_bars,
)


def _active_window(
    symbol: str, package: ResearchDatasetPackage, start: date, end: date
) -> tuple[date, date]:
    lo, hi = start, end
    ids = [r for r in package.identity if r.symbol == symbol]
    if ids:
        lo = max(lo, min(r.valid_from for r in ids))
        if all(r.valid_to is not None for r in ids):
            hi = min(hi, max(r.valid_to for r in ids if r.valid_to is not None))
    dels = [d for d in package.delistings if d.symbol == symbol]
    dels += [
        d
        for d in package.delistings
        if d.isin
        and any(b.isin == d.isin and b.symbol == symbol for b in package.ohlcv)
    ]
    if dels:
        hi = min(hi, min(d.delisting_date for d in dels))
    return lo, hi


def _missing_sessions(
    package: ResearchDatasetPackage, start: date, end: date
) -> dict[str, list[str]]:
    open_dates = {c.session_date for c in package.calendar if c.is_open}
    observed: dict[str, set[date]] = {}
    for b in package.ohlcv:
        observed.setdefault(b.symbol, set()).add(b.date)
    out: dict[str, list[str]] = {}
    for sym, obs in observed.items():
        lo, hi = _active_window(sym, package, start, end)
        expected = {d for d in open_dates if lo <= d <= hi}
        gap = sorted(expected - obs)
        if gap:
            out[sym] = [d.isoformat() for d in gap]
    return out


def certify_calendar(package: ResearchDatasetPackage) -> CertResult:
    start = package.manifest.coverage_start
    end = package.manifest.coverage_end

    duplicate_bars = detect_duplicate_bars(package.ohlcv)
    missing = _missing_sessions(package, start, end)
    closed_bars = detect_closed_session_bars(package.ohlcv, package.calendar)
    unexpected = detect_unexpected_bars(package.ohlcv, package.calendar)

    missing_count = sum(len(v) for v in missing.values())
    calendar_errors = missing_count + len(closed_bars) + len(unexpected)

    blockers: list[str] = []
    if not package.calendar:
        blockers.append("no authoritative calendar (calendar_verified=false)")
    if duplicate_bars:
        blockers.append(f"duplicate_bars={len(duplicate_bars)}")
    if missing_count:
        blockers.append(f"missing_sessions={missing_count}")
    if closed_bars:
        blockers.append(f"closed_session_bars={len(closed_bars)}")
    if unexpected:
        blockers.append(f"unexpected_bars={len(unexpected)}")

    calendar_verified = (
        bool(package.calendar) and calendar_errors == 0 and not duplicate_bars
    )

    open_dates = {c.session_date for c in package.calendar if c.is_open}
    return CertResult(
        dimension="calendar",
        passed=calendar_verified,
        metrics={
            "calendar_verified": calendar_verified,
            "calendar_errors": calendar_errors,
            "expected_sessions": len({d for d in open_dates if start <= d <= end}),
            "observed_sessions": len({b.date for b in package.ohlcv}),
            "missing_sessions": missing_count,
            "closed_session_bars": len(closed_bars),
            "unexpected_bars": len(unexpected),
            "duplicate_bars": len(duplicate_bars),
        },
        blockers=blockers,
    )

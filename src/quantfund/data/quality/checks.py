"""Calendar-aware quality checks distinguishing expected absence vs errors."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from quantfund.data.calendar.base import CalendarProvider
from quantfund.data.calendar.metadata import CALENDAR_UNVERIFIED_WARNING
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.grades import SourceGrade
from quantfund.data.identity import (
    check_active_symbol_conflicts,
    check_instrument_identity,
    check_isin_collision_registry,
    check_overlapping_listing_intervals,
)
from quantfund.data.instruments.delisted import (
    TerminalEvent,
    check_delisting_terminal_consistency,
)
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.providers.capabilities import ProviderCapabilities
from quantfund.data.quality.report import QualityIssue, QualityReport, Severity
from quantfund.data.universe.membership import MembershipAnswer, was_member
from quantfund.data.universe.models import UniverseCompleteness, UniverseVersion


def _bar_date(bar: MarketBar) -> date:
    return bar.timestamp.date() if isinstance(bar.timestamp, datetime) else bar.timestamp


def run_quality_checks(
    bars: list[MarketBar],
    *,
    calendar: CalendarProvider,
    universe: UniverseVersion | None = None,
    actions: list[CorporateAction] | None = None,
    instruments: list[Instrument] | None = None,
    terminal_events: list[TerminalEvent] | None = None,
    provider_capabilities: ProviderCapabilities | None = None,
    expected_package_hash: str | None = None,
    observed_package_hash: str | None = None,
    dataset_id: str | None = None,
    source: str | None = None,
    start: date | None = None,
    end: date | None = None,
    asof_date: date | None = None,
    stale_unchanged_sessions: int = 5,
) -> QualityReport:
    """Validate bars against calendar and research integrity rules.

    Saturday/Sunday and exchange holidays are INFO expected absences, not errors.
    Missing bars on open sessions are ERRORs.
    """
    cal_meta = calendar.metadata()
    report = QualityReport(
        dataset_id=dataset_id,
        source=source,
        universe_id=universe.universe_id if universe else None,
        universe_version=universe.universe_version if universe else None,
        calendar_id=calendar.calendar_id,
        calendar_version=calendar.calendar_version,
        calendar_verified=calendar.verified,
        corporate_action_count=len(actions or []),
    )

    if not calendar.verified:
        report.add(
            QualityIssue(
                severity=Severity.WARNING,
                code="calendar_unverified",
                message=CALENDAR_UNVERIFIED_WARNING,
                details=cal_meta.to_manifest_dict(),
            )
        )

    if not bars:
        report.add(
            QualityIssue(
                severity=Severity.ERROR,
                code="empty_bars",
                message="No bars provided for quality checks",
            )
        )
        return report

    symbols = sorted({b.symbol for b in bars})
    report.instrument_count = len(symbols)
    report.row_count = len(bars)

    dates = [_bar_date(b) for b in bars]
    d0 = start or min(dates)
    d1 = end or max(dates)
    report.date_range_start = d0.isoformat()
    report.date_range_end = d1.isoformat()

    # Refuse future corporate actions relative to as-of / last bar date
    asof = asof_date or d1
    for action in actions or []:
        if action.ex_date > asof:
            report.corporate_action_inconsistencies += 1
            report.add(
                QualityIssue(
                    severity=Severity.ERROR,
                    code="future_corporate_action_visible",
                    message=(
                        f"Corporate action {action.action_id} ex_date "
                        f"{action.ex_date.isoformat()} is after as-of {asof.isoformat()}"
                    ),
                    symbol=action.symbol,
                    timestamp=action.ex_date.isoformat(),
                )
            )

    expected = calendar.expected_sessions(d0, d1)

    # Count weekend/holiday days in range as expected absences (INFO).
    cursor = d0
    expected_absences = 0
    while cursor <= d1:
        if cursor not in expected:
            session = calendar.describe_day(cursor)
            report.add(
                QualityIssue(
                    severity=Severity.INFO,
                    code="expected_absence",
                    message=f"{cursor.isoformat()} is {session.session_type.value}",
                    timestamp=cursor.isoformat(),
                    details={"session_type": session.session_type.value},
                )
            )
            expected_absences += 1
        cursor = date.fromordinal(cursor.toordinal() + 1)
    report.expected_absences = expected_absences

    by_symbol: dict[str, list[MarketBar]] = defaultdict(list)
    for bar in bars:
        by_symbol[bar.symbol].append(bar)

    missing_session_dates: set[date] = set()

    for symbol, symbol_bars in by_symbol.items():
        symbol_bars_sorted = sorted(symbol_bars, key=lambda b: b.timestamp)
        seen: set[date] = set()
        prev_ts: datetime | None = None
        prev_close: float | None = None
        stale_run = 0
        for bar in symbol_bars_sorted:
            bd = _bar_date(bar)
            # Duplicate session
            if bd in seen:
                report.duplicate_bars += 1
                report.invalid_rows += 1
                report.add(
                    QualityIssue(
                        severity=Severity.ERROR,
                        code="duplicate_bar",
                        message=f"Duplicate bar for {symbol} on {bd.isoformat()}",
                        symbol=symbol,
                        timestamp=bd.isoformat(),
                    )
                )
            seen.add(bd)

            if prev_ts is not None and bar.timestamp < prev_ts:
                report.timestamp_problems += 1
                report.invalid_rows += 1
                report.add(
                    QualityIssue(
                        severity=Severity.ERROR,
                        code="chronology",
                        message=f"Out-of-order timestamp for {symbol}",
                        symbol=symbol,
                        timestamp=bar.timestamp.isoformat(),
                    )
                )
            prev_ts = bar.timestamp

            # OHLC already validated by MarketBar for positive prices / relationships;
            # still count any residual invalid patterns for report completeness.
            if bar.high < bar.low or bar.high < max(bar.open, bar.close) or bar.low > min(
                bar.open, bar.close
            ):
                report.invalid_ohlc += 1
                report.add(
                    QualityIssue(
                        severity=Severity.ERROR,
                        code="invalid_ohlc",
                        message=f"Invalid OHLC relationships for {symbol}",
                        symbol=symbol,
                        timestamp=bd.isoformat(),
                    )
                )

            if bar.volume < 0:
                report.negative_or_zero_volume += 1
                report.add(
                    QualityIssue(
                        severity=Severity.ERROR,
                        code="negative_volume",
                        message=f"Negative volume for {symbol}",
                        symbol=symbol,
                        timestamp=bd.isoformat(),
                    )
                )
            elif bar.volume == 0 and bd in expected:
                report.negative_or_zero_volume += 1
                report.add(
                    QualityIssue(
                        severity=Severity.WARNING,
                        code="zero_volume",
                        message=f"Zero volume on session {bd.isoformat()} for {symbol}",
                        symbol=symbol,
                        timestamp=bd.isoformat(),
                    )
                )

            if prev_close is not None and bar.close == prev_close and bar.open == prev_close:
                stale_run += 1
                if stale_run >= stale_unchanged_sessions:
                    report.stale_prices += 1
                    report.add(
                        QualityIssue(
                            severity=Severity.WARNING,
                            code="stale_price",
                            message=(
                                f"Stale unchanged prices for {symbol} over "
                                f"{stale_run} sessions ending {bd.isoformat()}"
                            ),
                            symbol=symbol,
                            timestamp=bd.isoformat(),
                        )
                    )
                    stale_run = 0  # avoid spam; recount from here
            else:
                stale_run = 0

            # Extreme discontinuity (not auto-repaired; may be CA or data error)
            if prev_close is not None and prev_close > 0:
                move = abs(bar.open - prev_close) / prev_close
                if move >= 0.5:
                    ca_on_day = [
                        a
                        for a in (actions or [])
                        if a.symbol == symbol
                        and a.ex_date == bd
                        and a.action_type
                        in {
                            CorporateActionType.SPLIT,
                            CorporateActionType.BONUS,
                            CorporateActionType.RIGHTS,
                        }
                    ]
                    if ca_on_day:
                        report.add(
                            QualityIssue(
                                severity=Severity.INFO,
                                code="ca_consistent_discontinuity",
                                message=(
                                    f"Large open gap for {symbol} on {bd.isoformat()} "
                                    f"coincides with {ca_on_day[0].action_type.value} "
                                    f"— not auto-repaired"
                                ),
                                symbol=symbol,
                                timestamp=bd.isoformat(),
                                details={
                                    "prev_close": prev_close,
                                    "open": bar.open,
                                    "move": move,
                                    "action_id": ca_on_day[0].action_id,
                                },
                            )
                        )
                    else:
                        report.add(
                            QualityIssue(
                                severity=Severity.WARNING,
                                code="extreme_discontinuity",
                                message=(
                                    f"Extreme open gap for {symbol} on {bd.isoformat()}: "
                                    f"prev_close={prev_close} open={bar.open} "
                                    f"({move:.1%}) — not auto-repaired"
                                ),
                                symbol=symbol,
                                timestamp=bd.isoformat(),
                                details={
                                    "prev_close": prev_close,
                                    "open": bar.open,
                                    "move": move,
                                },
                            )
                        )
            prev_close = bar.close

        missing = sorted(expected - seen)
        report.missing_bars += len(missing)
        for md in missing:
            missing_session_dates.add(md)
            report.add(
                QualityIssue(
                    severity=Severity.ERROR,
                    code="missing_open_session",
                    message=(
                        f"Missing bar for {symbol} on expected open session "
                        f"{md.isoformat()}"
                    ),
                    symbol=symbol,
                    timestamp=md.isoformat(),
                )
            )

    report.missing_sessions = len(missing_session_dates)

    for action in actions or []:
        if action.requires_manual_treatment:
            report.corporate_action_inconsistencies += 1
            report.add(
                QualityIssue(
                    severity=Severity.WARNING,
                    code="manual_corporate_action",
                    message=(
                        f"{action.action_type.value} for {action.symbol} on "
                        f"{action.ex_date.isoformat()} requires manual/verified treatment"
                    ),
                    symbol=action.symbol,
                    timestamp=action.ex_date.isoformat(),
                )
            )
        if action.action_type == CorporateActionType.SYMBOL_CHANGE:
            # Symbol changes must not invent new instrument_ids silently
            if not action.instrument_id:
                report.corporate_action_inconsistencies += 1
                report.add(
                    QualityIssue(
                        severity=Severity.ERROR,
                        code="symbol_change_missing_instrument_id",
                        message="SYMBOL_CHANGE without instrument_id",
                        symbol=action.symbol,
                        timestamp=action.ex_date.isoformat(),
                    )
                )

    if instruments:
        for issue in check_instrument_identity(instruments):
            if "identity" in issue.code:
                report.instrument_identity_problems += 1
            report.add(issue)
        for issue in check_isin_collision_registry(instruments):
            report.instrument_identity_problems += 1
            report.add(issue)
        for issue in check_active_symbol_conflicts(instruments):
            report.instrument_identity_problems += 1
            report.add(issue)
        for issue in check_overlapping_listing_intervals(instruments):
            report.instrument_identity_problems += 1
            report.add(issue)
        if terminal_events is not None:
            for issue in check_delisting_terminal_consistency(instruments, terminal_events):
                if issue.severity == Severity.ERROR:
                    report.instrument_identity_problems += 1
                report.add(issue)

    # Post-delisting bars are ERROR (never invent post-delist prices)
    if instruments:
        delist_by_symbol = {
            i.symbol: i.delisting_date for i in instruments if i.delisting_date
        }
        for bar in bars:
            dd = delist_by_symbol.get(bar.symbol)
            if dd is not None and _bar_date(bar) > dd:
                report.add(
                    QualityIssue(
                        severity=Severity.ERROR,
                        code="post_delisting_bar",
                        message=(
                            f"Bar for {bar.symbol} on {_bar_date(bar).isoformat()} "
                            f"after delisting_date {dd.isoformat()}"
                        ),
                        symbol=bar.symbol,
                        timestamp=_bar_date(bar).isoformat(),
                    )
                )

    # Unexpected bar on verified closed session
    for bar in bars:
        bd = _bar_date(bar)
        if not calendar.is_session(bd):
            session = calendar.describe_day(bd)
            report.add(
                QualityIssue(
                    severity=Severity.ERROR,
                    code="bar_on_closed_session",
                    message=(
                        f"Unexpected bar for {bar.symbol} on closed session "
                        f"{bd.isoformat()} ({session.session_type.value})"
                    ),
                    symbol=bar.symbol,
                    timestamp=bd.isoformat(),
                    details={"session_type": session.session_type.value},
                )
            )

    # Timezone / session-date inconsistency (naive timestamps OK if date aligns)
    for bar in bars:
        ts = bar.timestamp
        if isinstance(ts, datetime) and ts.tzinfo is not None:
            # Require Asia/Kolkata-compatible offset or UTC with matching calendar date
            offset = ts.utcoffset()
            if offset is not None and abs(offset.total_seconds()) not in {
                0,
                5.5 * 3600,
            }:
                report.add(
                    QualityIssue(
                        severity=Severity.ERROR,
                        code="timezone_session_inconsistency",
                        message=(
                            f"Bar timezone offset {offset} unexpected for NSE session dating"
                        ),
                        symbol=bar.symbol,
                        timestamp=ts.isoformat(),
                    )
                )

    # CA date inconsistencies vs listing
    if instruments and actions:
        listing = {
            (i.instrument_id or i.symbol): i.listing_date
            for i in instruments
            if i.listing_date
        }
        for action in actions:
            ld = listing.get(action.instrument_id) or listing.get(action.symbol)
            if ld is not None and action.ex_date < ld:
                report.corporate_action_inconsistencies += 1
                report.add(
                    QualityIssue(
                        severity=Severity.ERROR,
                        code="ca_before_listing",
                        message=(
                            f"Corporate action {action.action_id} ex_date "
                            f"{action.ex_date} before listing {ld}"
                        ),
                        symbol=action.symbol,
                        timestamp=action.ex_date.isoformat(),
                    )
                )

    # Capability forgery / checksum mismatch
    if (
        expected_package_hash is not None
        and observed_package_hash is not None
        and expected_package_hash != observed_package_hash
    ):
        report.add(
            QualityIssue(
                severity=Severity.ERROR,
                code="package_checksum_mismatch",
                message="Package content hash does not match recorded provenance hash",
                details={
                    "expected": expected_package_hash,
                    "observed": observed_package_hash,
                },
            )
        )

    if provider_capabilities is not None:
        grade = provider_capabilities.source_grade
        if grade in {SourceGrade.SYNTHETIC, SourceGrade.NON_EXCHANGE} and (
            provider_capabilities.exchange_authority
        ):
            report.add(
                QualityIssue(
                    severity=Severity.ERROR,
                    code="capability_forgery",
                    message=(
                        "Provider capabilities claim exchange_authority "
                        f"with source_grade={grade.value}"
                    ),
                )
            )
        pid = provider_capabilities.provider_id.lower()
        if pid in {"yfinance", "synthetic", "synthetic_fixture"} and (
            provider_capabilities.can_satisfy_research_eligibility_source_bar()
        ):
            report.add(
                QualityIssue(
                    severity=Severity.ERROR,
                    code="capability_forgery",
                    message=f"provider_id={pid} cannot satisfy research source bar",
                )
            )

    if universe is not None:
        for w in universe.warnings:
            report.add(
                QualityIssue(
                    severity=Severity.WARNING,
                    code="universe_warning",
                    message=w,
                )
            )

        # Detect today's constituents applied across historical range.
        # ERROR for research claims (eligibility gate); WARNING here so
        # development datasets can still build while remaining development_only.
        if universe.completeness == UniverseCompleteness.CURRENT_SNAPSHOT_ONLY:
            if d0 != universe.as_of_date or d1 != universe.as_of_date:
                report.add(
                    QualityIssue(
                        severity=Severity.WARNING,
                        code="current_snapshot_used_as_history",
                        message=(
                            "Stage A current_snapshot_only universe applied across "
                            f"[{d0} .. {d1}] (as_of={universe.as_of_date}). "
                            "Today's constituents must not stand in for history — "
                            "blocks research_eligible."
                        ),
                        details={
                            "as_of_date": universe.as_of_date.isoformat(),
                            "range_start": d0.isoformat(),
                            "range_end": d1.isoformat(),
                        },
                    )
                )

        # Count UNKNOWN membership sessions for known symbols in range
        unknown_count = 0
        sample_symbols = symbols[: min(len(symbols), 50)]
        for sym in sample_symbols:
            cur = d0
            while cur <= d1:
                if cur in expected:
                    ans = was_member(universe, symbol=sym, on=cur)
                    if ans == MembershipAnswer.UNKNOWN:
                        unknown_count += 1
                cur = date.fromordinal(cur.toordinal() + 1)
        report.unknown_membership_periods = unknown_count
        if unknown_count > 0:
            report.add(
                QualityIssue(
                    severity=Severity.WARNING,
                    code="unknown_membership_periods",
                    message=(
                        f"{unknown_count} symbol-session pairs have UNKNOWN membership "
                        "(UNKNOWN ≠ FALSE; trading blocked for UNKNOWN)"
                    ),
                    details={"count": unknown_count},
                )
            )

        # Delisted instruments silently removed from historical universe
        if instruments:
            for inst in instruments:
                if inst.delisting_date and d0 <= inst.delisting_date <= d1:
                    # Should still appear in PIT membership history
                    if universe.completeness == UniverseCompleteness.CURRENT_SNAPSHOT_ONLY:
                        report.add(
                            QualityIssue(
                                severity=Severity.ERROR,
                                code="delisted_silently_removed",
                                message=(
                                    f"Delisted instrument {inst.symbol} "
                                    f"(delisted {inst.delisting_date}) cannot be "
                                    "represented under current_snapshot_only"
                                ),
                                symbol=inst.symbol,
                            )
                        )
                    elif universe.memberships:
                        ever = any(
                            m.instrument_id == inst.instrument_id
                            for m in universe.memberships
                        )
                        if not ever:
                            report.add(
                                QualityIssue(
                                    severity=Severity.WARNING,
                                    code="delisted_missing_from_pit",
                                    message=(
                                        f"Delisted instrument {inst.symbol} absent from "
                                        "PIT membership intervals"
                                    ),
                                    symbol=inst.symbol,
                                )
                            )

        # Future membership visibility (as-of leak): only when caller pins asof_date.
        # Full PIT ledgers may extend past a dataset's bar window without being a leak.
        if asof_date is not None:
            for m in universe.memberships:
                if m.member_from > asof_date:
                    report.add(
                        QualityIssue(
                            severity=Severity.ERROR,
                            code="future_membership_visible",
                            message=(
                                f"Membership for {m.symbol} starts {m.member_from} "
                                f"after as-of {asof_date} (lookahead leak)"
                            ),
                            symbol=m.symbol,
                            timestamp=m.member_from.isoformat(),
                        )
                    )

    return report

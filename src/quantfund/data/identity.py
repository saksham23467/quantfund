"""Instrument identity helpers — ticker is not permanent identity."""

from __future__ import annotations

from datetime import date, timedelta

from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.models import Instrument, SymbolHistoryEntry
from quantfund.data.quality.report import QualityIssue, Severity

# Phase 5 identity policy (code-documented; not a toggle).
IDENTITY_POLICY = {
    "permanent_id": "exchange:ISIN when ISIN known; never ticker-alone",
    "rename": "symbol_history update; instrument_id unchanged",
    "merger_demerger": "manual TerminalEvent; no automatic OHLC stitch",
    "collision": "same ISIN / instrument_id mapping to conflicting entities without history → ERROR",
}


def resolve_instrument_id(
    *,
    exchange: str | None,
    isin: str | None,
    symbol: str,
) -> str:
    if isin and exchange:
        return f"{exchange}:{isin}"
    if exchange:
        return f"{exchange}:{symbol}"
    return f"UNKNOWN:{symbol}"


def apply_symbol_change(
    instrument: Instrument,
    action: CorporateAction,
    *,
    new_symbol: str,
) -> Instrument:
    """Record a symbol change without inventing a new company identity.

    Mergers/demergers must not use this helper — they require manual treatment.
    """
    if action.action_type != CorporateActionType.SYMBOL_CHANGE:
        raise ValueError("apply_symbol_change requires SYMBOL_CHANGE action")
    if action.instrument_id and instrument.instrument_id != action.instrument_id:
        raise ValueError(
            "symbol change instrument_id mismatch — refusing to treat as new company"
        )

    history = list(instrument.symbol_history)
    prior_end = action.ex_date - timedelta(days=1)
    # Close previous open-ended history entry
    closed: list[SymbolHistoryEntry] = []
    for entry in history:
        if entry.valid_to is None and entry.valid_from <= prior_end:
            closed.append(
                SymbolHistoryEntry(
                    symbol=entry.symbol,
                    valid_from=entry.valid_from,
                    valid_to=max(entry.valid_from, prior_end),
                    exchange=entry.exchange,
                )
            )
        else:
            closed.append(entry)

    if not closed:
        # Seed history with the pre-change symbol
        closed.append(
            SymbolHistoryEntry(
                symbol=instrument.symbol,
                valid_from=instrument.listing_date or prior_end,
                valid_to=prior_end,
                exchange=instrument.exchange,
            )
        )

    closed.append(
        SymbolHistoryEntry(
            symbol=new_symbol,
            valid_from=action.ex_date,
            valid_to=None,
            exchange=instrument.exchange,
        )
    )

    return instrument.model_copy(
        update={
            "symbol": new_symbol,
            "symbol_history": closed,
            "metadata": {
                **instrument.metadata,
                "last_symbol_change_ex_date": action.ex_date.isoformat(),
                "prior_symbol": instrument.symbol,
            },
        }
    )


def check_instrument_identity(instruments: list[Instrument]) -> list[QualityIssue]:
    """Flag identity problems that undermine research trust."""
    issues: list[QualityIssue] = []
    seen_ids: dict[str, Instrument] = {}
    for inst in instruments:
        iid = inst.instrument_id or resolve_instrument_id(
            exchange=inst.exchange, isin=inst.isin, symbol=inst.symbol
        )
        if iid.startswith("UNKNOWN:"):
            issues.append(
                QualityIssue(
                    severity=Severity.WARNING,
                    code="instrument_identity_weak",
                    message=f"{inst.symbol} lacks exchange+ISIN stable identity",
                    symbol=inst.symbol,
                )
            )
        if iid in seen_ids:
            other = seen_ids[iid]
            if other.symbol != inst.symbol and not (
                inst.symbol_history or other.symbol_history
            ):
                issues.append(
                    QualityIssue(
                        severity=Severity.ERROR,
                        code="instrument_identity_collision",
                        message=(
                            f"instrument_id {iid} maps to both "
                            f"{other.symbol} and {inst.symbol} without symbol_history"
                        ),
                        symbol=inst.symbol,
                    )
                )
        seen_ids[iid] = inst

        if inst.delisting_date and inst.listing_date:
            if inst.delisting_date < inst.listing_date:
                issues.append(
                    QualityIssue(
                        severity=Severity.ERROR,
                        code="instrument_identity_dates",
                        message=f"{inst.symbol} delisting_date before listing_date",
                        symbol=inst.symbol,
                    )
                )
    return issues


def check_isin_collision_registry(instruments: list[Instrument]) -> list[QualityIssue]:
    """ERROR if same ISIN maps to conflicting economic identities without history."""
    issues: list[QualityIssue] = []
    by_isin: dict[str, list[Instrument]] = {}
    for inst in instruments:
        if not inst.isin:
            continue
        by_isin.setdefault(inst.isin, []).append(inst)
    for isin, group in by_isin.items():
        ids = {i.instrument_id for i in group}
        if len(ids) > 1:
            # Allow only if symbol_history links them as renames of one id — else ERROR
            issues.append(
                QualityIssue(
                    severity=Severity.ERROR,
                    code="isin_identity_collision",
                    message=(
                        f"ISIN {isin} maps to multiple instrument_ids: {sorted(ids)}"
                    ),
                    details={"isin": isin, "instrument_ids": sorted(ids)},
                )
            )
    return issues


def check_active_symbol_conflicts(instruments: list[Instrument]) -> list[QualityIssue]:
    """ERROR if the same symbol maps to multiple simultaneously active instruments."""
    issues: list[QualityIssue] = []
    active_by_symbol: dict[str, list[Instrument]] = {}
    for inst in instruments:
        if inst.delisting_date is not None:
            continue
        active_by_symbol.setdefault(inst.symbol, []).append(inst)
    for sym, group in active_by_symbol.items():
        ids = {i.instrument_id for i in group}
        if len(ids) > 1:
            issues.append(
                QualityIssue(
                    severity=Severity.ERROR,
                    code="active_symbol_conflict",
                    message=(
                        f"Symbol {sym} maps to multiple active instrument_ids: "
                        f"{sorted(ids)}"
                    ),
                    symbol=sym,
                    details={"instrument_ids": sorted(ids)},
                )
            )
    return issues


def check_overlapping_listing_intervals(
    instruments: list[Instrument],
) -> list[QualityIssue]:
    """WARNING/ERROR when listing intervals for the same ISIN overlap inconsistently."""
    issues: list[QualityIssue] = []
    by_isin: dict[str, list[Instrument]] = {}
    for inst in instruments:
        if not inst.isin or not inst.listing_date:
            continue
        by_isin.setdefault(inst.isin, []).append(inst)
    for isin, group in by_isin.items():
        if len(group) < 2:
            continue
        for i, a in enumerate(group):
            a_end = a.delisting_date or date.max
            for b in group[i + 1 :]:
                b_end = b.delisting_date or date.max
                if a.listing_date <= b_end and b.listing_date <= a_end:
                    if a.instrument_id != b.instrument_id:
                        issues.append(
                            QualityIssue(
                                severity=Severity.ERROR,
                                code="overlapping_listing_interval",
                                message=(
                                    f"ISIN {isin} has overlapping listing intervals "
                                    f"for {a.instrument_id} and {b.instrument_id}"
                                ),
                                details={"isin": isin},
                            )
                        )
    return issues

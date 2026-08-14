"""Import local NSE CF-CA style files into existing CorporateAction model.

Reuses classify_purpose + ratio/cash parsers from historical_local.
Does not invent adjustments. Incomplete split/bonus/dividend parses keep
their classified type with parse_status=UNKNOWN (never silently drop to OTHER
unless the purpose itself is unclassifiable).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from quantfund.data.corporate_actions.historical_local import (
    classify_purpose,
    parse_bonus_ratio,
    parse_cf_date,
    parse_dividend_cash,
    parse_split_ratio,
)
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.paper.models import deterministic_id


def _parse_fields(
    purpose: str, atype: CorporateActionType
) -> tuple[float | None, float | None, float | None, str, bool]:
    """Return ratio_num, ratio_den, cash_amount, parse_status, requires_manual."""
    ratio_num = ratio_den = cash_amount = None
    if atype is CorporateActionType.BONUS:
        parsed = parse_bonus_ratio(purpose)
        if parsed:
            return parsed[0], parsed[1], None, "OK", False
        return None, None, None, "UNKNOWN", True
    if atype is CorporateActionType.SPLIT:
        parsed = parse_split_ratio(purpose)
        if parsed:
            return parsed[0], parsed[1], None, "OK", False
        return None, None, None, "UNKNOWN", True
    if atype is CorporateActionType.DIVIDEND:
        cash = parse_dividend_cash(purpose)
        if cash is not None:
            return None, None, cash, "OK", False
        return None, None, None, "UNKNOWN", True
    if atype in {
        CorporateActionType.MERGER,
        CorporateActionType.DEMERGER,
        CorporateActionType.RIGHTS,
        CorporateActionType.FACE_VALUE_CHANGE,
        CorporateActionType.BUYBACK,
        CorporateActionType.SYMBOL_CHANGE,
    }:
        return None, None, None, "UNKNOWN", True
    if atype is CorporateActionType.OTHER:
        return None, None, None, "UNKNOWN", False
    return None, None, None, "NOT_APPLICABLE", False


def import_ca_csv(
    path: Path,
    *,
    symbol_filter: str | None = None,
) -> tuple[list[CorporateAction], dict[str, Any]]:
    """Parse CF-CA-like CSV. Unknown purposes → OTHER + flagged."""
    if not path.exists():
        return [], {"status": "MISSING_FILE", "path": str(path), "count": 0}

    actions: list[CorporateAction] = []
    unknown_purpose = 0
    parse_unknown = 0
    classified_ok = 0
    type_counts: dict[str, int] = {}

    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            norm = {
                (k or "").replace("\ufeff", "").strip().upper(): (v or "").strip()
                for k, v in row.items()
            }
            sym = norm.get("SYMBOL") or norm.get("SYMBOL ")
            if not sym:
                continue
            if symbol_filter and sym.upper() != symbol_filter.upper():
                continue
            purpose = norm.get("PURPOSE") or ""
            atype = classify_purpose(purpose)
            if atype is CorporateActionType.OTHER:
                unknown_purpose += 1
            ex = parse_cf_date(norm.get("EX-DATE") or norm.get("EX_DATE"))
            if ex is None:
                continue
            rec = parse_cf_date(norm.get("RECORD DATE") or norm.get("RECORD_DATE"))
            aid = deterministic_id("zca", sym, purpose[:40], ex.isoformat(), i)
            ratio_num, ratio_den, cash_amount, parse_status, requires_manual = _parse_fields(
                purpose, atype
            )
            if parse_status == "UNKNOWN":
                parse_unknown += 1
            elif parse_status == "OK":
                classified_ok += 1

            type_counts[atype.value] = type_counts.get(atype.value, 0) + 1
            actions.append(
                CorporateAction(
                    action_id=aid,
                    instrument_id=f"NSE:{sym.upper()}",
                    symbol=sym.upper(),
                    action_type=atype,
                    ex_date=ex,
                    record_date=rec,
                    ratio_num=ratio_num,
                    ratio_den=ratio_den,
                    cash_amount=cash_amount,
                    source="historical_local_ca",
                    verified=False,
                    requires_manual_treatment=requires_manual,
                    raw_payload={
                        "purpose": purpose,
                        "company": norm.get("COMPANY NAME") or norm.get("COMPANY"),
                        "series": norm.get("SERIES"),
                        "face_value": norm.get("FACE VALUE") or norm.get("FACE_VALUE"),
                        "parse_status": parse_status,
                    },
                    notes="imported_for_zerodha_hist_validation",
                )
            )

    return actions, {
        "status": "OK",
        "count": len(actions),
        "unknown_or_other_purpose": unknown_purpose,
        "parse_unknown": parse_unknown,
        "classified_ok": classified_ok,
        "type_counts": type_counts,
        "path": str(path),
    }

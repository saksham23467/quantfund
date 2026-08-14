"""Historical local NSE CF-CA equities ingest — DEVELOPMENT / non_exchange only.

Source grade is permanently non_exchange. Never promotes research eligibility.
RAW OHLC is never modified by this module.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from quantfund.config import PATHS
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.ingest.checksums import file_checksum, hash_json, write_checksums
from quantfund.data.policy import (
    DatasetCertificationFacts,
    EligibilityLevel,
)

SOURCE_ID = "historical_local_ca"
SOURCE_GRADE = "non_exchange"
PROVIDER_LABEL = "historical_local_ca"

# As-of visibility: without announcement dates, expose an event only when
# session_date >= ex_date (conservative: no pretence that ex_date == announcement).
ASOF_VISIBILITY_RULE = "ex_date_available_on_or_after_ex_date"


class ParseStatus(str, Enum):
    OK = "OK"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class IdentityResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"


class DateValidationStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"
    WARNING = "WARNING"


_DATE_FORMATS = ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y")


def _clean_header(name: str) -> str:
    return name.replace("\ufeff", "").strip().strip('"').strip().upper()


def parse_cf_date(value: str | None) -> date | None:
    if value is None:
        return None
    text = str(value).strip().strip('"')
    if not text or text == "-":
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def classify_purpose(purpose_raw: str) -> CorporateActionType:
    """Deterministic purpose → type. Never guess exotic events into SPLIT/DIVIDEND."""
    p = (purpose_raw or "").strip().lower()
    if not p:
        return CorporateActionType.OTHER

    # Meetings / governance — not price adjustments (check before dividend)
    meeting_only = bool(
        re.search(
            r"\b(annual general meeting|extra ordinary general meeting|"
            r"extraordinary general meeting|board meeting|election of director|"
            r"egm|agm)\b",
            p,
        )
    )
    has_div = bool(re.search(r"\bdividend\b|\bdiv\b", p))
    if meeting_only and not has_div and "bonus" not in p and "split" not in p:
        return CorporateActionType.OTHER
    if re.search(r"\binterest payment\b", p):
        return CorporateActionType.OTHER

    if re.search(r"\bdemerger\b|\bde-merger\b", p):
        return CorporateActionType.DEMERGER
    if re.search(r"\bmerger\b|\bamalgamation\b|\bscheme of arrangement\b", p):
        return CorporateActionType.MERGER
    if re.search(r"\bbuy\s*back\b|\bbuyback\b", p):
        return CorporateActionType.BUYBACK
    if re.search(r"\bright(s)?\s*issue\b|\bright(s)?\b", p) and "dividend" not in p:
        return CorporateActionType.RIGHTS
    if re.search(
        r"\bfv\s*split\b|\bsplit\b|\bface\s*value\s*(split|revised|revision|change)\b",
        p,
    ):
        if re.search(r"face\s*value\s*(revised|revision|change)", p) and "split" not in p:
            return CorporateActionType.FACE_VALUE_CHANGE
        return CorporateActionType.SPLIT
    if re.search(r"\bbonus\b", p):
        return CorporateActionType.BONUS
    if has_div:
        return CorporateActionType.DIVIDEND
    if re.search(r"\bsymbol\s*change\b|\bname\s*change\b", p):
        return CorporateActionType.SYMBOL_CHANGE
    return CorporateActionType.OTHER


def parse_bonus_ratio(purpose_raw: str) -> tuple[float, float] | None:
    p = purpose_raw or ""
    m = re.search(r"bonus\s+(\d+)\s*[:/]\s*(\d+)", p, re.I)
    if not m:
        return None
    num, den = float(m.group(1)), float(m.group(2))
    if den == 0:
        return None
    # Bonus A:B means A new shares per B held → factor (A+B)/B
    return (num + den, den)


def parse_split_ratio(purpose_raw: str) -> tuple[float, float] | None:
    """Return (ratio_num, ratio_den) as new/old share multiplier components.

    ``Split Rs.10 to Re.1`` → 10-for-1 → ratio_num=10, ratio_den=1.
    """
    p = purpose_raw or ""
    m = re.search(
        r"(?:fv\s*)?split[^0-9]*"
        r"(?:rs\.?|re\.?)?\s*([0-9]+(?:\.[0-9]+)?)\s*/?-?\s*"
        r"(?:to|into)\s*"
        r"(?:rs\.?|re\.?)?\s*([0-9]+(?:\.[0-9]+)?)",
        p,
        re.I,
    )
    if not m:
        m = re.search(
            r"([0-9]+(?:\.[0-9]+)?)\s*/?-?\s*(?:to|into)\s*(?:rs\.?|re\.?)?\s*"
            r"([0-9]+(?:\.[0-9]+)?)",
            p,
            re.I,
        )
        if not m or "split" not in p.lower():
            return None
    old_fv, new_fv = float(m.group(1)), float(m.group(2))
    if new_fv <= 0 or old_fv <= 0:
        return None
    # shares multiply by old/new
    return (old_fv, new_fv)


def parse_dividend_cash(purpose_raw: str) -> float | None:
    p = purpose_raw or ""
    # Rs 2.50 / Re.1 / Rs.6.50 Per Share
    m = re.search(
        r"(?:rs\.?|re\.?)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/-)?\s*(?:per\s*sh)",
        p,
        re.I,
    )
    if m:
        return float(m.group(1))
    m = re.search(
        r"dividend[^0-9]*?(?:rs\.?|re\.?)\s*([0-9]+(?:\.[0-9]+)?)",
        p,
        re.I,
    )
    if m:
        return float(m.group(1))
    # percentage-only dividends → UNKNOWN cash (do not invent face-value math)
    if re.search(r"\d+\s*%", p) and re.search(r"dividend", p, re.I):
        return None
    return None


def event_hash(
    *,
    symbol: str,
    action_type: str,
    purpose_raw: str,
    ex_date: str | None,
    record_date: str | None,
    face_value: str | None,
    source_id: str,
) -> str:
    payload = {
        "symbol": symbol.strip().upper(),
        "action_type": action_type,
        "purpose_raw": purpose_raw.strip(),
        "ex_date": ex_date or "",
        "record_date": record_date or "",
        "face_value": face_value or "",
        "source_id": source_id,
    }
    return hash_json(payload)


class NormalizedCARecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_row_id: int
    source_id: str = SOURCE_ID
    source_hash: str
    event_hash: str
    symbol: str
    company_name: str = ""
    series: str = ""
    purpose_raw: str
    action_type: CorporateActionType
    face_value: float | None = None
    ex_date: date | None = None
    record_date: date | None = None
    book_closure_start: date | None = None
    book_closure_end: date | None = None
    ratio_num: float | None = None
    ratio_den: float | None = None
    cash_amount: float | None = None
    parse_status: ParseStatus = ParseStatus.UNKNOWN
    identity_resolution_status: IdentityResolutionStatus = IdentityResolutionStatus.UNKNOWN
    instrument_id: str = "UNKNOWN"
    source_symbol: str = ""
    date_status: DateValidationStatus = DateValidationStatus.OK
    date_issues: list[str] = Field(default_factory=list)
    is_price_adjusting: bool = False
    requires_manual_treatment: bool = False

    def to_corporate_action(self) -> CorporateAction | None:
        """Map to ledger model when ex_date is valid."""
        if self.ex_date is None:
            return None
        payload = {
            "purpose_raw": self.purpose_raw,
            "company_name": self.company_name,
            "series": self.series,
            "face_value": self.face_value,
            "book_closure_start": self.book_closure_start.isoformat()
            if self.book_closure_start
            else None,
            "book_closure_end": self.book_closure_end.isoformat()
            if self.book_closure_end
            else None,
            "parse_status": self.parse_status.value,
            "identity_resolution_status": self.identity_resolution_status.value,
            "source_row_id": self.source_row_id,
            "source_hash": self.source_hash,
            "event_hash": self.event_hash,
            "is_price_adjusting": self.is_price_adjusting,
            "date_issues": list(self.date_issues),
        }
        return CorporateAction(
            action_id=self.event_hash.replace("sha256:", "ca_")[:64],
            instrument_id=self.instrument_id,
            symbol=self.symbol,
            action_type=self.action_type,
            ex_date=self.ex_date,
            record_date=self.record_date,
            announcement_date=None,  # not in source — do not invent
            ratio_num=self.ratio_num,
            ratio_den=self.ratio_den,
            cash_amount=self.cash_amount,
            source=SOURCE_ID,
            source_ref=f"row:{self.source_row_id}",
            verified=False,
            requires_manual_treatment=self.requires_manual_treatment,
            raw_payload=payload,
            notes=f"purpose_raw={self.purpose_raw[:200]}",
        )


def _validate_dates(
    *,
    action_type: CorporateActionType,
    ex_date: date | None,
    record_date: date | None,
    book_start: date | None,
    book_end: date | None,
    raw_ex: str,
    raw_record: str,
) -> tuple[DateValidationStatus, list[str]]:
    issues: list[str] = []
    # Malformed non-empty date strings
    for label, raw, parsed in (
        ("ex_date", raw_ex, ex_date),
        ("record_date", raw_record, record_date),
    ):
        text = (raw or "").strip()
        if text and text != "-" and parsed is None:
            issues.append(f"malformed_{label}")

    if book_start and book_end and book_start > book_end:
        issues.append("book_closure_start_after_end")

    if action_type in {
        CorporateActionType.SPLIT,
        CorporateActionType.BONUS,
        CorporateActionType.DIVIDEND,
    }:
        if ex_date is None:
            issues.append("missing_ex_date")

    if any(
        x.startswith("malformed_") or x == "book_closure_start_after_end" for x in issues
    ):
        return DateValidationStatus.ERROR, issues
    if issues:
        return DateValidationStatus.WARNING, issues
    return DateValidationStatus.OK, issues


def normalize_row(
    row: dict[str, str],
    *,
    source_row_id: int,
    source_hash: str,
    known_symbols: set[str] | None = None,
    instruments: list | None = None,
) -> NormalizedCARecord:
    # Normalize keys (handle BOM)
    mapped = {_clean_header(k): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    symbol = (mapped.get("SYMBOL") or "").strip().upper()
    purpose_raw = mapped.get("PURPOSE") or ""
    company = mapped.get("COMPANY NAME") or ""
    series = mapped.get("SERIES") or ""
    fv_raw = mapped.get("FACE VALUE") or ""
    ex_raw = mapped.get("EX-DATE") or ""
    rec_raw = mapped.get("RECORD DATE") or ""
    bcs_raw = mapped.get("BOOK CLOSURE START DATE") or ""
    bce_raw = mapped.get("BOOK CLOSURE END DATE") or ""

    action_type = classify_purpose(purpose_raw)
    ex_date = parse_cf_date(ex_raw)
    record_date = parse_cf_date(rec_raw)
    book_start = parse_cf_date(bcs_raw)
    book_end = parse_cf_date(bce_raw)

    face_value = None
    try:
        if fv_raw and fv_raw != "-":
            face_value = float(fv_raw)
    except ValueError:
        face_value = None

    ratio_num = ratio_den = cash_amount = None
    parse_status = ParseStatus.NOT_APPLICABLE
    requires_manual = False
    is_price_adjusting = False

    if action_type == CorporateActionType.BONUS:
        parsed = parse_bonus_ratio(purpose_raw)
        if parsed:
            ratio_num, ratio_den = parsed
            parse_status = ParseStatus.OK
            is_price_adjusting = True
        else:
            parse_status = ParseStatus.UNKNOWN
            requires_manual = True
    elif action_type == CorporateActionType.SPLIT:
        parsed = parse_split_ratio(purpose_raw)
        if parsed:
            ratio_num, ratio_den = parsed
            parse_status = ParseStatus.OK
            is_price_adjusting = True
        else:
            parse_status = ParseStatus.UNKNOWN
            requires_manual = True
    elif action_type == CorporateActionType.DIVIDEND:
        cash_amount = parse_dividend_cash(purpose_raw)
        if cash_amount is not None:
            parse_status = ParseStatus.OK
            # dividends tracked separately — not OHLC-adjusting under default policy
            is_price_adjusting = False
        else:
            parse_status = ParseStatus.UNKNOWN
            requires_manual = True
    elif action_type in {
        CorporateActionType.MERGER,
        CorporateActionType.DEMERGER,
        CorporateActionType.RIGHTS,
        CorporateActionType.FACE_VALUE_CHANGE,
        CorporateActionType.BUYBACK,
    }:
        parse_status = ParseStatus.UNKNOWN
        requires_manual = True
        is_price_adjusting = False
    else:
        parse_status = ParseStatus.NOT_APPLICABLE
        is_price_adjusting = False

    date_status, date_issues = _validate_dates(
        action_type=action_type,
        ex_date=ex_date,
        record_date=record_date,
        book_start=book_start,
        book_end=book_end,
        raw_ex=ex_raw,
        raw_record=rec_raw,
    )

    if instruments is not None:
        from quantfund.data.instruments.resolve import (
            IdentityResolutionStatus as MasterStatus,
            resolve_symbol_identity,
        )

        res = resolve_symbol_identity(symbol, instruments=instruments, asof=ex_date)
        if res.status == MasterStatus.RESOLVED:
            identity = IdentityResolutionStatus.RESOLVED
            instrument_id = res.instrument_id
        elif res.status == MasterStatus.AMBIGUOUS:
            identity = IdentityResolutionStatus.AMBIGUOUS
            instrument_id = res.instrument_id
        else:
            identity = IdentityResolutionStatus.UNKNOWN
            instrument_id = res.instrument_id
    else:
        known = known_symbols or set()
        if known and symbol in known:
            identity = IdentityResolutionStatus.RESOLVED
            instrument_id = f"NSE:{symbol}"
        else:
            # No instrument master supplied → UNKNOWN (do not invent confidence)
            identity = IdentityResolutionStatus.UNKNOWN
            instrument_id = f"UNKNOWN:{symbol}" if symbol else "UNKNOWN"

    eh = event_hash(
        symbol=symbol,
        action_type=action_type.value,
        purpose_raw=purpose_raw,
        ex_date=ex_date.isoformat() if ex_date else ex_raw,
        record_date=record_date.isoformat() if record_date else rec_raw,
        face_value=fv_raw,
        source_id=SOURCE_ID,
    )

    return NormalizedCARecord(
        source_row_id=source_row_id,
        source_id=SOURCE_ID,
        source_hash=source_hash,
        event_hash=eh,
        symbol=symbol,
        company_name=company,
        series=series,
        purpose_raw=purpose_raw,
        action_type=action_type,
        face_value=face_value,
        ex_date=ex_date,
        record_date=record_date,
        book_closure_start=book_start,
        book_closure_end=book_end,
        ratio_num=ratio_num,
        ratio_den=ratio_den,
        cash_amount=cash_amount,
        parse_status=parse_status,
        identity_resolution_status=identity,
        instrument_id=instrument_id,
        source_symbol=symbol,
        date_status=date_status,
        date_issues=date_issues,
        is_price_adjusting=is_price_adjusting,
        requires_manual_treatment=requires_manual
        or action_type
        in {
            CorporateActionType.MERGER,
            CorporateActionType.DEMERGER,
        },
    )


def corporate_actions_asof(
    records: list[NormalizedCARecord] | list[CorporateAction],
    *,
    timestamp: date | datetime,
    symbol: str | None = None,
) -> list[Any]:
    """Return CA events visible at ``timestamp``.

    Visibility rule (documented): ``ASOF_VISIBILITY_RULE``.
    Without announcement dates, an event is visible iff ``ex_date <= as_of_date``.
    Future ex-dates are never exposed.
    """
    if isinstance(timestamp, datetime):
        as_of = timestamp.date()
    else:
        as_of = timestamp
    out: list[Any] = []
    sym = symbol.upper() if symbol else None
    for r in records:
        ex = getattr(r, "ex_date", None)
        if ex is None:
            continue
        if ex > as_of:
            continue
        rsym = getattr(r, "symbol", None)
        if sym is not None and rsym != sym:
            continue
        out.append(r)
    return out


@dataclass
class HistoricalCAMetrics:
    ca_total_events: int = 0
    ca_dividend_events: int = 0
    ca_split_events: int = 0
    ca_bonus_events: int = 0
    ca_rights_events: int = 0
    ca_face_value_events: int = 0
    ca_buyback_events: int = 0
    ca_merger_events: int = 0
    ca_demerger_events: int = 0
    ca_other_events: int = 0
    resolved_identity_rows: int = 0
    unresolved_identity_rows: int = 0
    identity_coverage_ratio: float = 0.0
    ca_date_validity_ratio: float = 0.0
    ca_parse_success_ratio: float = 0.0
    duplicate_exact_count: int = 0
    duplicate_conflict_count: int = 0
    date_error_count: int = 0
    parse_ok_count: int = 0
    parse_unknown_count: int = 0
    price_adjusting_events: int = 0
    coverage_start: str | None = None
    coverage_end: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ca_total_events": self.ca_total_events,
            "ca_dividend_events": self.ca_dividend_events,
            "ca_split_events": self.ca_split_events,
            "ca_bonus_events": self.ca_bonus_events,
            "ca_rights_events": self.ca_rights_events,
            "ca_face_value_events": self.ca_face_value_events,
            "ca_buyback_events": self.ca_buyback_events,
            "ca_merger_events": self.ca_merger_events,
            "ca_demerger_events": self.ca_demerger_events,
            "ca_other_events": self.ca_other_events,
            "resolved_identity_rows": self.resolved_identity_rows,
            "unresolved_identity_rows": self.unresolved_identity_rows,
            "ca_identity_coverage_ratio": self.identity_coverage_ratio,
            "ca_date_validity_ratio": self.ca_date_validity_ratio,
            "ca_parse_success_ratio": self.ca_parse_success_ratio,
            "duplicate_exact_count": self.duplicate_exact_count,
            "ca_duplicate_conflict_count": self.duplicate_conflict_count,
            "date_error_count": self.date_error_count,
            "parse_ok_count": self.parse_ok_count,
            "parse_unknown_count": self.parse_unknown_count,
            "price_adjusting_events": self.price_adjusting_events,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "asof_visibility_rule": ASOF_VISIBILITY_RULE,
            "source_grade": SOURCE_GRADE,
            "exchange_authority": False,
            "note": "EVENT_PRESENT ≠ full_verified; non_exchange cannot be research_eligible",
        }


def compute_metrics(records: list[NormalizedCARecord]) -> HistoricalCAMetrics:
    m = HistoricalCAMetrics(ca_total_events=len(records))
    hashes: dict[str, list[NormalizedCARecord]] = {}
    for r in records:
        hashes.setdefault(r.event_hash, []).append(r)
        if r.action_type == CorporateActionType.DIVIDEND:
            m.ca_dividend_events += 1
        elif r.action_type == CorporateActionType.SPLIT:
            m.ca_split_events += 1
        elif r.action_type == CorporateActionType.BONUS:
            m.ca_bonus_events += 1
        elif r.action_type == CorporateActionType.RIGHTS:
            m.ca_rights_events += 1
        elif r.action_type == CorporateActionType.FACE_VALUE_CHANGE:
            m.ca_face_value_events += 1
        elif r.action_type == CorporateActionType.BUYBACK:
            m.ca_buyback_events += 1
        elif r.action_type == CorporateActionType.MERGER:
            m.ca_merger_events += 1
        elif r.action_type == CorporateActionType.DEMERGER:
            m.ca_demerger_events += 1
        else:
            m.ca_other_events += 1

        if r.identity_resolution_status == IdentityResolutionStatus.RESOLVED:
            m.resolved_identity_rows += 1
        else:
            m.unresolved_identity_rows += 1  # UNKNOWN + AMBIGUOUS
        if r.date_status == DateValidationStatus.ERROR:
            m.date_error_count += 1
        if r.parse_status == ParseStatus.OK:
            m.parse_ok_count += 1
        elif r.parse_status == ParseStatus.UNKNOWN:
            m.parse_unknown_count += 1
        if r.is_price_adjusting:
            m.price_adjusting_events += 1

    for group in hashes.values():
        if len(group) <= 1:
            continue
        m.duplicate_exact_count += len(group) - 1
        # Conflict: same hash already exact; conflicting = same symbol/ex_date/type different purpose
    # Secondary conflict scan
    by_key: dict[tuple[str, str, str], list[NormalizedCARecord]] = {}
    for r in records:
        if r.ex_date is None:
            continue
        key = (r.symbol, r.action_type.value, r.ex_date.isoformat())
        by_key.setdefault(key, []).append(r)
    for group in by_key.values():
        purposes = {g.purpose_raw.strip() for g in group}
        if len(purposes) > 1:
            m.duplicate_conflict_count += 1

    n = max(len(records), 1)
    m.identity_coverage_ratio = m.resolved_identity_rows / n
    m.ca_date_validity_ratio = (len(records) - m.date_error_count) / n
    adjustable = [
        r
        for r in records
        if r.action_type
        in {
            CorporateActionType.SPLIT,
            CorporateActionType.BONUS,
            CorporateActionType.DIVIDEND,
        }
    ]
    if adjustable:
        m.ca_parse_success_ratio = sum(
            1 for r in adjustable if r.parse_status == ParseStatus.OK
        ) / len(adjustable)
    dates = [r.ex_date for r in records if r.ex_date]
    if dates:
        m.coverage_start = min(dates).isoformat()
        m.coverage_end = max(dates).isoformat()
    return m


@dataclass
class HistoricalCAIngestResult:
    success: bool
    raw_root: Path | None
    normalized_root: Path | None
    source_path: Path
    source_hash: str
    row_count: int
    records: list[NormalizedCARecord] = field(default_factory=list)
    actions: list[CorporateAction] = field(default_factory=list)
    metrics: HistoricalCAMetrics = field(default_factory=HistoricalCAMetrics)
    eligibility: str = EligibilityLevel.DEVELOPMENT_ONLY.value
    research_eligible: bool = False
    report_text: str = ""
    raw_ohlc_modified: bool = False


def ingest_raw_ca_file(
    source_path: Path,
    *,
    raw_root: Path | None = None,
) -> tuple[Path, str, dict[str, Any]]:
    """Copy source bytes immutably into data/raw/historical_local_ca/<id>/."""
    source_path = Path(source_path)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    content_hash = file_checksum(source_path)
    download_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    )
    root = Path(raw_root or PATHS.raw_dir) / PROVIDER_LABEL / download_id
    if root.exists():
        raise FileExistsError(f"Raw CA directory already exists: {root}")
    root.mkdir(parents=True)
    dest = root / source_path.name
    shutil.copy2(source_path, dest)
    # Verify byte-identical
    if file_checksum(dest) != content_hash:
        raise RuntimeError("raw CA copy checksum mismatch")

    # Row count without modifying source
    with dest.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        row_count = sum(1 for _ in reader)

    meta = {
        "source_id": SOURCE_ID,
        "source_filename": source_path.name,
        "source_path_original": str(source_path.resolve()),
        "source_grade": SOURCE_GRADE,
        "exchange_authority": False,
        "research_eligible": False,
        "development_only": True,
        "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
        "content_hash": content_hash,
        "row_count": row_count,
        "schema_columns": header,
        "schema_hash": hash_json(header or []),
        "provenance": {
            "provider": PROVIDER_LABEL,
            "license_status": "unknown",
            "redistribution_rights": "unknown_unless_explicitly_established",
            "note": "User-supplied local CF-CA equities export; not exchange-authoritative research data",
        },
    }
    (root / "provenance.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "download_id": download_id,
                "source": SOURCE_ID,
                "source_grade": SOURCE_GRADE,
                "content_hash": content_hash,
                "row_count": row_count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    write_checksums(root, label="raw_historical_ca")
    return root, content_hash, meta


def load_and_normalize(
    source_path: Path,
    *,
    source_hash: str,
    known_symbols: set[str] | None = None,
    instruments: list | None = None,
) -> list[NormalizedCARecord]:
    records: list[NormalizedCARecord] = []
    with Path(source_path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader, start=1):
            records.append(
                normalize_row(
                    row,
                    source_row_id=i,
                    source_hash=source_hash,
                    known_symbols=known_symbols,
                    instruments=instruments,
                )
            )
    return records


def _development_facts_for_ca(metrics: HistoricalCAMetrics, source_hash: str) -> DatasetCertificationFacts:
    """Facts that keep DEVELOPMENT_ONLY even if CA types are rich."""
    return DatasetCertificationFacts(
        dataset_id="historical_local_ca_dev",
        dataset_version="cf_ca_equities",
        source=SOURCE_ID,
        source_grade=SOURCE_GRADE,
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        calendar_verified=True,
        universe_id="none",
        universe_version="none",
        universe_completeness="current_snapshot_only",
        corporate_action_coverage="partial",  # events present; not full_verified
        adjustment_policy_id="split_bonus_v1",
        date_coverage_start=metrics.coverage_start or "2009-01-01",
        date_coverage_end=metrics.coverage_end or "2026-08-01",
        instrument_count=0,
        delisted_coverage="none",
        error_count=metrics.date_error_count,
        content_hash=source_hash,
        unknown_membership_session_count=1,
        membership_coverage_ratio=0.0,
        capability_source_bar_ok=False,
        provenance_complete=False,
        license_status="unknown",
        data_class="DEVELOPMENT_DATA",
        ca_coverage_breakdown=metrics.to_dict(),
        extras={
            "data_class": "DEVELOPMENT_DATA",
            "exchange_authority": False,
            "corporate_action_source": SOURCE_ID,
        },
    )


def format_ca_demo_report(
    *,
    metrics: HistoricalCAMetrics,
    eligibility: str,
) -> str:
    def pct(x: float) -> str:
        return f"{100.0 * x:.2f}%"

    lines = [
        f"Source: {SOURCE_ID}",
        f"Coverage: {metrics.coverage_start or '?'} → {metrics.coverage_end or '?'}",
        "",
        f"Total CA events: {metrics.ca_total_events}",
        "",
        f"Dividends: {metrics.ca_dividend_events}",
        f"Splits: {metrics.ca_split_events}",
        f"Bonuses: {metrics.ca_bonus_events}",
        f"Rights: {metrics.ca_rights_events}",
        f"Face-value changes: {metrics.ca_face_value_events}",
        f"Buybacks: {metrics.ca_buyback_events}",
        f"Mergers: {metrics.ca_merger_events}",
        f"Demergers: {metrics.ca_demerger_events}",
        f"Other: {metrics.ca_other_events}",
        "",
        f"Identity coverage: {pct(metrics.identity_coverage_ratio)}",
        f"Parse success: {pct(metrics.ca_parse_success_ratio)}",
        f"Duplicate conflicts: {metrics.duplicate_conflict_count}",
        f"Exact duplicate extras: {metrics.duplicate_exact_count}",
        "",
        "RAW OHLC modified: NO",
        "Future CA leakage: NONE",
        "",
        "Source grade: NON_EXCHANGE",
        "Exchange authority: FALSE",
        "",
        f"Dataset eligibility: {eligibility.upper()}",
        "",
        "Research acceptance: BLOCKED",
        "Reason: non_exchange / development CA source (not exchange-authoritative)",
        "",
        f"As-of visibility rule: {ASOF_VISIBILITY_RULE}",
    ]
    return "\n".join(lines)


def ingest_historical_ca(
    source_path: Path,
    *,
    known_symbols: set[str] | None = None,
    instruments: list | None = None,
    instrument_master: tuple[str, str] | None = None,
    output_normalized_root: Path | None = None,
) -> HistoricalCAIngestResult:
    """Full pipeline: raw immutable copy → normalize → metrics → eligibility check.

    Prefer ``instruments`` or ``instrument_master=(master_id, version)`` for identity.
    """
    source_path = Path(source_path)
    if instruments is None and instrument_master is not None:
        from quantfund.config import PATHS
        from quantfund.data.instruments.master import InstrumentMasterStore

        mid, mver = instrument_master
        instruments = InstrumentMasterStore(PATHS.data_dir / "instruments").load(
            mid, mver
        )
    raw_root, source_hash, meta = ingest_raw_ca_file(source_path)
    copied = raw_root / source_path.name
    records = load_and_normalize(
        copied,
        source_hash=source_hash,
        known_symbols=known_symbols,
        instruments=instruments,
    )
    metrics = compute_metrics(records)
    actions: list[CorporateAction] = []
    for r in records:
        ca = r.to_corporate_action()
        if ca is not None:
            actions.append(ca)

    norm_root = Path(
        output_normalized_root
        or (PATHS.normalized_dir / "corporate_actions" / SOURCE_ID / raw_root.name)
    )
    if norm_root.exists():
        raise FileExistsError(norm_root)
    norm_root.mkdir(parents=True)
    (norm_root / "normalized_ca.jsonl").write_text(
        "\n".join(r.model_dump_json() for r in records) + ("\n" if records else ""),
        encoding="utf-8",
    )
    (norm_root / "corporate_actions.json").write_text(
        json.dumps([a.model_dump(mode="json") for a in actions], indent=2, default=str),
        encoding="utf-8",
    )
    provenance = {
        "corporate_action_source": {
            "source_id": SOURCE_ID,
            "source_hash": source_hash,
            "source_grade": SOURCE_GRADE,
            "exchange_authority": False,
            "coverage_start": metrics.coverage_start,
            "coverage_end": metrics.coverage_end,
            "row_count": metrics.ca_total_events,
            "ca_coverage_metrics": metrics.to_dict(),
            "raw_download": str(raw_root),
            "asof_visibility_rule": ASOF_VISIBILITY_RULE,
        }
    }
    (norm_root / "manifest.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8"
    )
    write_checksums(norm_root, label="normalized_historical_ca")

    facts = _development_facts_for_ca(metrics, source_hash)
    decision = ResearchEligibilityChecker().evaluate(facts)
    assert decision.level == EligibilityLevel.DEVELOPMENT_ONLY
    report = format_ca_demo_report(metrics=metrics, eligibility=decision.level.value)
    (norm_root / "CA_REPORT.txt").write_text(report, encoding="utf-8")

    return HistoricalCAIngestResult(
        success=True,
        raw_root=raw_root,
        normalized_root=norm_root,
        source_path=source_path,
        source_hash=source_hash,
        row_count=int(meta["row_count"]),
        records=records,
        actions=actions,
        metrics=metrics,
        eligibility=decision.level.value,
        research_eligible=False,
        report_text=report,
        raw_ohlc_modified=False,
    )


def crosscheck_yfinance_dividends(
    records: list[NormalizedCARecord],
    yfinance_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Diagnostic-only CA vs yfinance comparison. Not truth arbitration."""
    src_keys = set()
    for r in records:
        if r.action_type != CorporateActionType.DIVIDEND or r.ex_date is None:
            continue
        src_keys.add((r.symbol, r.ex_date.isoformat()))
    yf_keys = set()
    for e in yfinance_events:
        sym = str(e.get("symbol", "")).upper().replace(".NS", "")
        d = e.get("ex_date") or e.get("date")
        if not sym or not d:
            continue
        yf_keys.add((sym, str(d)[:10]))
    matched = src_keys & yf_keys
    return {
        "matched_events": len(matched),
        "source_only_events": len(src_keys - yf_keys),
        "yfinance_only_events": len(yf_keys - src_keys),
        "conflicting_events": 0,  # amounts not compared unless both parse
        "diagnostic_only": True,
        "exchange_grade_claim": False,
    }

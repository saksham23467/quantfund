"""Corporate-action coverage for Phase 17A — no invented adjustments."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from quantfund.data.corporate_actions.adjust import apply_adjustment_policy
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.corporate_actions.policies import default_split_bonus_policy
from quantfund.data.models import MarketBar
from quantfund.data.zerodha_hist.ca_import import import_ca_csv


KNOWN_ADJUSTABLE = frozenset(
    {CorporateActionType.SPLIT, CorporateActionType.BONUS}
)
KNOWN_TRACKED = frozenset(
    {
        CorporateActionType.SPLIT,
        CorporateActionType.BONUS,
        CorporateActionType.DIVIDEND,
        CorporateActionType.RIGHTS,
        CorporateActionType.MERGER,
        CorporateActionType.DEMERGER,
        CorporateActionType.FACE_VALUE_CHANGE,
        CorporateActionType.BUYBACK,
        CorporateActionType.SYMBOL_CHANGE,
    }
)


def default_ca_file() -> Path | None:
    root = Path.cwd()
    candidates = [
        root / "CF-CA-equities-01-01-2009-to-01-08-2026.csv",
        root / "tests" / "fixtures" / "ca" / "cf_ca_sample.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def ca_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def analyze_ca_for_symbol(
    symbol: str,
    *,
    ca_file: Path | None,
    bars: list[MarketBar] | None = None,
) -> dict[str, Any]:
    if ca_file is None or not ca_file.exists():
        return {
            "symbol": symbol,
            "events": 0,
            "known": 0,
            "unknown": 0,
            "coverage": "NONE",
            "blockers": ["ca_file_missing"],
            "types": {},
            "price_policy": {
                "raw_execution": True,
                "research_adjusted_invented": False,
                "adjustment_policy_id": None,
            },
        }
    actions, meta = import_ca_csv(ca_file, symbol_filter=symbol)
    types: dict[str, int] = {}
    known = 0
    unknown = 0
    parse_unknown = 0
    for a in actions:
        types[a.action_type.value] = types.get(a.action_type.value, 0) + 1
        if a.action_type is CorporateActionType.OTHER:
            unknown += 1
        elif a.action_type in KNOWN_TRACKED:
            known += 1
        else:
            unknown += 1
        if (a.raw_payload or {}).get("parse_status") == "UNKNOWN":
            parse_unknown += 1

    blockers: list[str] = []
    coverage = "NONE"
    if actions:
        # Local CF-CA is never treated as exchange-complete coverage.
        coverage = "PARTIAL"
        if unknown:
            blockers.append("unknown_or_other_ca_types_present")
        if parse_unknown:
            blockers.append("ca_events_with_unknown_parse_status")
        if not any(
            a.action_type in KNOWN_ADJUSTABLE
            and (a.raw_payload or {}).get("parse_status") == "OK"
            for a in actions
        ):
            blockers.append("no_parsed_split_bonus_events_in_window_or_file")

    adj_summary = None
    policy = default_split_bonus_policy()
    if bars and actions:
        adjusted = apply_adjustment_policy(bars, actions, policy)
        changed = sum(
            1
            for ab in adjusted
            if ab.adjustment_factor != 1.0
            and ab.adj_close is not None
            and ab.adj_close != ab.raw.close
        )
        adj_summary = {
            "policy_id": policy.policy_id,
            "bars_with_nonzero_adjustment": changed,
            "raw_ohlc_mutated": False,
            "note": "Adjusted columns derived separately; RAW execution prices unchanged",
        }

    return {
        "symbol": symbol,
        "events": len(actions),
        "known": known,
        "unknown": unknown,
        "parse_unknown": parse_unknown,
        "coverage": coverage,
        "blockers": blockers,
        "types": types,
        "ca_meta": meta,
        "adjustment": adj_summary,
        "price_policy": {
            "raw_execution": True,
            "research_adjusted_invented": False,
            "adjustment_policy_id": policy.policy_id,
            "dividends_in_ohlc": policy.adjust_dividends_in_ohlc,
        },
        "actions": actions,
    }


def ca_coverage_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        out.append(
            {
                "symbol": r["symbol"],
                "events": r["events"],
                "known": r["known"],
                "unknown": r["unknown"],
                "coverage": r["coverage"],
                "blockers": r["blockers"],
            }
        )
    return out

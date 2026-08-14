"""PIT instrument identity and universe membership audit for Phase 17C.

Does not invent membership. Reports UNKNOWN where architecture requires PIT
and package lacks a membership ledger.
"""

from __future__ import annotations

import json
from typing import Any

from quantfund.data.models import MarketBar
from quantfund.phase17a.datasets import DiscoveredPackage


def audit_instrument_identity(pkg: DiscoveredPackage) -> dict[str, Any]:
    meta_path = pkg.path / "instrument_metadata.json"
    meta: dict[str, Any] = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # Resolver output may be stored at the top level or nested under "resolved".
    # Read both so genuinely-present identity fields (e.g. instrument_token) are
    # not falsely reported missing. This never invents identity: absent values
    # stay absent and still fail closed.
    resolved = meta.get("resolved") if isinstance(meta.get("resolved"), dict) else {}

    def _field(*keys: str) -> Any:
        for key in keys:
            val = meta.get(key)
            if val:
                return val
        for key in keys:
            val = resolved.get(key)
            if val:
                return val
        return None

    token = _field("instrument_token", "token")
    exchange = _field("exchange") or pkg.manifest.get("exchange") or "NSE"
    tradingsymbol = _field("tradingsymbol", "symbol") or pkg.symbol
    instrument_id = _field("instrument_id") or f"{exchange}:{pkg.symbol}"
    isin = _field("isin")
    issues: list[str] = []
    if not token:
        issues.append("missing_instrument_token")
    if not tradingsymbol:
        issues.append("missing_tradingsymbol")
    # Broker-resolved NSE:SYMBOL without a real ISIN is not exchange-ISIN PIT
    # identity. Value-based check: a null/absent ISIN fails closed.
    if not isin and str(instrument_id).startswith("NSE:"):
        issues.append("no_isin_stable_identity")
    return {
        "symbol": pkg.symbol,
        "instrument_id": instrument_id,
        "exchange": exchange,
        "tradingsymbol": tradingsymbol,
        "instrument_token": token,
        "isin": isin,
        "identity_status": "BROKER_RESOLVED" if token else "UNKNOWN",
        "pit_grade": "non_pit_broker_snapshot",
        "issues": issues,
        "issue_count": len(issues),
    }


def audit_universe_membership(
    pkg: DiscoveredPackage,
    bars: list[MarketBar],
) -> dict[str, Any]:
    """Evaluate membership coverage against package-local membership if present."""
    membership_path = None
    for name in ("universe/membership.json", "membership.json", "universe_membership.json"):
        cand = pkg.path / name
        if cand.exists():
            membership_path = cand
            break

    n = len(bars)
    if membership_path is None:
        sample = [b.timestamp.date().isoformat() for b in bars[:5]]
        return {
            "symbol": pkg.symbol,
            "membership_file": None,
            "membership_coverage": "none",
            "universe_completeness": "current_snapshot_only",
            "unknown_membership_session_count": n,
            "true_membership_session_count": 0,
            "false_membership_session_count": 0,
            "membership_coverage_ratio": 0.0,
            "sample_unknown_dates": sample,
            "blockers": [
                "missing_package_universe_membership_ledger",
                "unknown_membership_session_count_gt_0",
            ],
            "note": (
                "No PIT membership ledger in Zerodha package; "
                "every session is membership UNKNOWN (not invented as TRUE)."
            ),
        }

    # Ledger present but loading/interpreting is deferred to universe helpers;
    # without a typed UniverseVersion we still refuse to invent TRUE membership.
    return {
        "symbol": pkg.symbol,
        "membership_file": str(membership_path),
        "membership_coverage": "present_unparsed",
        "universe_completeness": "unknown",
        "unknown_membership_session_count": n,
        "true_membership_session_count": 0,
        "false_membership_session_count": 0,
        "membership_coverage_ratio": 0.0,
        "sample_unknown_dates": [b.timestamp.date().isoformat() for b in bars[:5]],
        "blockers": [
            "membership_ledger_present_but_not_full_pit_certified",
            "unknown_membership_session_count_gt_0",
        ],
        "note": "Membership file found; full PIT certification still required.",
    }

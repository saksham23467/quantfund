"""Phase 18 — research-dataset eligibility gate (dataset only; no strategy search).

This module DOES NOT weaken any eligibility gate, invent historical data, or
silently repair anything. It reuses the Phase 17C certification path and the
central ``ResearchEligibilityChecker`` verbatim, aggregates the honest facts
across the Zerodha research packages, and resolves the ordered blocker list from
the gap analysis. Where the genuine artifact/authority required to clear a
blocker does not exist, the blocker is reported UNRESOLVED and the gate fails
closed (``research_eligible = false``).

No paper trading, no live trading, and no broker order-placement occur here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.phase15.models import scrub_secrets
from quantfund.phase17a.ca import default_ca_file
from quantfund.phase17a.datasets import PREFERRED_SYMBOLS, discover_zerodha_packages
from quantfund.phase17c.pipeline import certify_symbol_package
from quantfund.phase17c.safety import safety_payload


# Ordered blocker resolution sequence (source of truth: Phase 17C gap analysis).
BLOCKER_ORDER: tuple[str, ...] = (
    "exchange_grade_source_certification",
    "calendar_residuals",
    "corporate_action_completeness",
    "pit_universe_membership_ledger",
    "instrument_identity_isin",
    "delisted_security_coverage",
    "capability_source_bar_ok",
)


def _union_blockers(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({b for r in rows for b in (r["eligibility"].get("blockers") or [])})


def _any_blocker(rows: list[dict[str, Any]], needle: str) -> bool:
    return any(needle in b for r in rows for b in (r["eligibility"].get("blockers") or []))


def _agg_int(rows: list[dict[str, Any]], path: tuple[str, ...]) -> int:
    total = 0
    for r in rows:
        node: Any = r
        for key in path:
            node = (node or {}).get(key) if isinstance(node, dict) else None
        try:
            total += int(node or 0)
        except (TypeError, ValueError):
            pass
    return total


def build_blocker_ledger(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve each ordered blocker against aggregated, honest per-symbol facts.

    A blocker is RESOLVED only when the certified facts already satisfy the
    central gate. Otherwise it is UNRESOLVED with an explicit fail-closed reason
    and the genuine artifact/authority that would be required (never invented).
    """
    identity_issues = _agg_int(rows, ("identity", "issue_count"))
    unknown_membership = _agg_int(rows, ("membership", "unknown_membership_session_count"))
    quality_errors = _agg_int(rows, ("quality", "errors"))

    ledger: list[dict[str, Any]] = []

    # 1. Exchange-grade source certification.
    src_blocked = _any_blocker(rows, "source_grade=non_exchange") or _any_blocker(
        rows, "data_class=DEVELOPMENT_DATA"
    )
    ledger.append(
        {
            "id": "exchange_grade_source_certification",
            "status": "UNRESOLVED" if src_blocked else "RESOLVED",
            "current_implementation": (
                "src/quantfund/data/providers/zerodha_historical.py:104-108 "
                "(source_grade=NON_EXCHANGE); "
                "src/quantfund/phase17c/certify_gate.py:38-63 "
                "(source_grade='non_exchange', data_class='DEVELOPMENT_DATA', "
                "never forged); gate in src/quantfund/data/eligibility.py:73-76,60-65"
            ),
            "evidence": {
                "source_grade": "non_exchange",
                "data_class": "DEVELOPMENT_DATA",
                "license_status": "broker_account_restricted",
            },
            "fail_closed_reason": (
                "Zerodha Kite historical is broker-redistributed data, not "
                "exchange-authoritative. Marking it exchange/paid grade would "
                "forge source authority, which is explicitly forbidden. No "
                "exchange-authority attestation exists in any package."
            ),
            "required_genuine_artifact": (
                "A market-data license/feed from an exchange-authoritative or "
                "paid research-grade vendor (e.g. official NSE EOD/tick or "
                "equivalent) with verifiable provenance. Cannot be synthesized."
            ),
        }
    )

    # 2. Calendar residuals.
    cal_blocked = _any_blocker(rows, "quality ERROR count") or quality_errors > 0
    ledger.append(
        {
            "id": "calendar_residuals",
            "status": "UNRESOLVED" if cal_blocked else "RESOLVED",
            "current_implementation": (
                "src/quantfund/data/calendar/nse.py (verified NSE calendar); "
                "src/quantfund/phase17a/quality.py:run_symbol_quality "
                "(bar_on_closed_session / missing_open_session ERRORs); "
                "gate in src/quantfund/data/eligibility.py:104-107"
            ),
            "evidence": {"aggregate_quality_error_count": quality_errors},
            "fail_closed_reason": (
                "Residual sessions (bar_on_closed_session / missing_open_session) "
                "reflect genuine calendar-vs-data mismatches. Resolving them by "
                "inserting or deleting bars would be silent data repair "
                "(forbidden), and correcting the certified calendar requires an "
                "authoritative NSE session/holiday source."
            ),
            "required_genuine_artifact": (
                "An authoritative NSE trading-session/holiday reference for the "
                "specific residual dates so the certified calendar can be "
                "reconciled against authority (never by mutating bars)."
            ),
        }
    )

    # 3. Corporate-action completeness (research bar = splits_bonus_dividends+).
    ca_blocked = _any_blocker(rows, "corporate_action_coverage=")
    ledger.append(
        {
            "id": "corporate_action_completeness",
            "status": "UNRESOLVED" if ca_blocked else "RESOLVED",
            "current_implementation": (
                "src/quantfund/phase17a/ca.py:analyze_ca_for_symbol; "
                "src/quantfund/data/corporate_actions/coverage.py:71-119; "
                "label mapping in src/quantfund/phase17c/pipeline.py:52-58; "
                "gate in src/quantfund/data/eligibility.py:98-103"
            ),
            "evidence": {
                "coverage_labels": sorted(
                    {str((r.get("corporate_actions") or {}).get("coverage")) for r in rows}
                ),
            },
            "fail_closed_reason": (
                "Research-bar CA coverage (splits_bonus_dividends) is derived only "
                "from CA events actually present; dividends/bonus/splits are not "
                "invented. Production still requires full_verified (stricter)."
            ),
            "required_genuine_artifact": (
                "For production candidacy: a fully verified corporate-action "
                "ledger (full_verified). Research bar is satisfied when genuine "
                "split/bonus/dividend events are present."
            ),
        }
    )

    # 4. PIT universe membership ledger.
    pit_blocked = (
        _any_blocker(rows, "universe_completeness")
        or _any_blocker(rows, "unknown_membership_session_count")
        or _any_blocker(rows, "membership_coverage_ratio")
    )
    ledger.append(
        {
            "id": "pit_universe_membership_ledger",
            "status": "UNRESOLVED" if pit_blocked else "RESOLVED",
            "current_implementation": (
                "src/quantfund/phase17c/identity_pit.py:audit_universe_membership "
                "(fails closed: no ledger => every session UNKNOWN, never TRUE); "
                "gate in src/quantfund/data/eligibility.py:87-132"
            ),
            "evidence": {
                "aggregate_unknown_membership_sessions": unknown_membership,
                "membership_ledger_present": False,
            },
            "fail_closed_reason": (
                "No point-in-time universe membership ledger exists in any "
                "package. Membership is reported UNKNOWN (not invented as TRUE). "
                "Today's snapshot must not stand in for history."
            ),
            "required_genuine_artifact": (
                "A point-in-time universe membership ledger: constituent "
                "membership intervals with verified flags for the traded "
                "universe. Absent; cannot be invented."
            ),
        }
    )

    # 5. Instrument identity / ISIN mapping.
    id_blocked = _any_blocker(rows, "instrument_identity_issues") or identity_issues > 0
    ledger.append(
        {
            "id": "instrument_identity_isin",
            "status": "UNRESOLVED" if id_blocked else "RESOLVED",
            "current_implementation": (
                "src/quantfund/phase17c/identity_pit.py:audit_instrument_identity "
                "(now reads nested 'resolved' fields; instrument_token surfaced, "
                "ISIN value-checked and fails closed when null); "
                "gate in src/quantfund/data/eligibility.py:142-145"
            ),
            "evidence": {
                "aggregate_identity_issue_count": identity_issues,
                "instrument_token_present": all(
                    bool((r.get("identity") or {}).get("instrument_token")) for r in rows
                )
                if rows
                else False,
                "isin_present": all(
                    bool((r.get("identity") or {}).get("isin")) for r in rows
                )
                if rows
                else False,
            },
            "fail_closed_reason": (
                "instrument_token is genuinely present (broker-resolved) and is "
                "now read correctly, removing a false 'missing_instrument_token'. "
                "ISIN is genuinely null and is not invented, so "
                "'no_isin_stable_identity' correctly remains."
            ),
            "required_genuine_artifact": (
                "Authoritative ISIN mapping (exchange:ISIN) per instrument from a "
                "trusted security master. Absent; cannot be invented."
            ),
        }
    )

    # 6. Delisted-security coverage.
    delisted_blocked = _any_blocker(rows, "delisted_coverage=")
    ledger.append(
        {
            "id": "delisted_security_coverage",
            "status": "UNRESOLVED" if delisted_blocked else "RESOLVED",
            "current_implementation": (
                "src/quantfund/phase17c/certify_gate.py:51 "
                "(delisted_coverage='unknown', honest); "
                "measurement in src/quantfund/data/instruments/coverage.py:42-127; "
                "gate in src/quantfund/data/eligibility.py:134-140"
            ),
            "evidence": {"delisted_coverage": "unknown"},
            "fail_closed_reason": (
                "No delisting / terminal-event ledger exists for the universe. "
                "Coverage is reported 'unknown' (not upgraded to partial/complete "
                "without evidence)."
            ),
            "required_genuine_artifact": (
                "A delisting / terminal-event ledger (delisting dates, survivor "
                "mapping) covering the universe. Absent; cannot be invented."
            ),
        }
    )

    # 7. capability_source_bar_ok (derived from source authority).
    cap_blocked = _any_blocker(rows, "capability_source_bar_ok=false")
    ledger.append(
        {
            "id": "capability_source_bar_ok",
            "status": "UNRESOLVED" if cap_blocked else "RESOLVED",
            "current_implementation": (
                "src/quantfund/data/providers/capabilities.py:61-71 "
                "(can_satisfy_research_eligibility_source_bar); "
                "src/quantfund/phase17c/certify_gate.py:60 (False); "
                "gate in src/quantfund/data/eligibility.py:77-84"
            ),
            "evidence": {"capability_source_bar_ok": False},
            "fail_closed_reason": (
                "Derived from source grade: a non_exchange provider cannot "
                "satisfy the research source bar. Resolves automatically once an "
                "exchange/paid-grade source (#1) is certified."
            ),
            "required_genuine_artifact": (
                "Same as exchange-grade source certification (#1)."
            ),
        }
    )

    return ledger


def run_phase18_dataset_eligibility(
    *,
    out_dir: Path | None = None,
    packages: list[Any] | None = None,
    write_reports: bool = True,
) -> dict[str, Any]:
    """Evaluate research-dataset eligibility only. Never enables trading."""
    root = Path.cwd()
    reports_dir = (out_dir / "reports") if out_dir else (root / "reports")
    docs_dir = (out_dir / "docs") if out_dir else (root / "docs")

    pkgs = packages if packages is not None else discover_zerodha_packages(
        symbols=PREFERRED_SYMBOLS
    )
    ca_file = default_ca_file()

    # write_package=False: read-only. Preserves immutable dataset versions.
    rows = [
        certify_symbol_package(pkg, ca_file=ca_file, write_package=False) for pkg in pkgs
    ]

    ledger = build_blocker_ledger(rows)
    ledger_by_id = {b["id"]: b for b in ledger}
    ordered = [ledger_by_id[bid] for bid in BLOCKER_ORDER]

    unresolved = [b for b in ordered if b["status"] == "UNRESOLVED"]
    stopped_at = unresolved[0]["id"] if unresolved else None

    research_eligible = bool(rows) and all(
        r["eligibility"]["is_research_eligible"] for r in rows
    )
    # paper_candidate requires research eligibility AND research acceptance
    # (strategy search), which is deliberately NOT performed here.
    accepted_strategies = "not_run"
    paper_candidate = bool(research_eligible) and accepted_strategies not in (0, "not_run")

    safety = safety_payload()

    payload = scrub_secrets(
        {
            "phase": "18",
            "stage": "research_dataset_eligibility",
            "statement": (
                "Phase 18 research-dataset eligibility gate only. "
                "NO STRATEGY SEARCH, NO PAPER TRADING, NO LIVE TRADING."
            ),
            "research_eligible": research_eligible,
            "paper_candidate": paper_candidate,
            "live_enabled": False,
            "orders_submitted": 0,
            "place_order_called": 0,
            "accepted_strategies": accepted_strategies,
            "symbols": [r["symbol"] for r in rows],
            "package_count": len(rows),
            "eligibility": {
                "aggregate": "RESEARCH_ELIGIBLE" if research_eligible else "DEVELOPMENT_ONLY",
                "any_research_eligible": any(
                    r["eligibility"]["is_research_eligible"] for r in rows
                ),
                "all_research_eligible": research_eligible,
                "levels": sorted({r["eligibility"]["level"] for r in rows}),
                "zerodha_shortcut": False,
                "remaining_blocker_strings": _union_blockers(rows),
            },
            "blocker_resolution_order": list(BLOCKER_ORDER),
            "blocker_ledger": ordered,
            "stopped_at_blocker": stopped_at,
            "per_symbol": [
                {
                    "symbol": r["symbol"],
                    "source_dataset_id": r["source_dataset_id"],
                    "source_dataset_version": r["source_dataset_version"],
                    "source_content_hash": r["source_content_hash"],
                    "in_window_bars": r["in_window_bars"],
                    "identity": r["identity"],
                    "membership": r["membership"],
                    "calendar": r.get("calendar"),
                    "quality": r.get("quality"),
                    "corporate_actions": {
                        k: (r.get("corporate_actions") or {}).get(k)
                        for k in ("events", "known", "unknown", "coverage", "types")
                    },
                    "eligibility": r["eligibility"],
                }
                for r in rows
            ],
            "immutability": {
                "source_versions_preserved": True,
                "wrote_new_dataset_versions": False,
                "note": (
                    "Eligibility evaluated read-only (write_package=False). "
                    "No dataset version was created or overwritten."
                ),
            },
            "safety": safety,
        }
    )

    if write_reports:
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "phase18_dataset_eligibility.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        write_phase18_eligibility_docs(
            payload, docs_dir / "PHASE18_DATASET_ELIGIBILITY.md"
        )

    return payload


def write_phase18_eligibility_docs(payload: dict[str, Any], path: Path) -> None:
    elig = payload.get("eligibility") or {}
    lines = [
        "# PHASE 18 — Research Dataset Eligibility",
        "",
        str(payload.get("statement") or ""),
        "",
        "## Final gate status",
        "",
        f"- `research_eligible = {str(payload.get('research_eligible')).lower()}`",
        f"- `paper_candidate = {str(payload.get('paper_candidate')).lower()}`",
        "- `live_enabled = false`",
        "- `orders_submitted = 0`",
        "- `place_order_called = 0`",
        f"- Eligibility aggregate: `{elig.get('aggregate')}`",
        f"- Any research-eligible: `{elig.get('any_research_eligible')}`",
        f"- Zerodha shortcut: `{elig.get('zerodha_shortcut')}`",
        f"- Stopped at blocker: `{payload.get('stopped_at_blocker')}`",
        "",
        "## Ordered blocker resolution",
        "",
        "| # | Blocker | Status | Fail-closed reason (summary) |",
        "|---|---|---|---|",
    ]
    for i, b in enumerate(payload.get("blocker_ledger") or [], start=1):
        reason = str(b.get("fail_closed_reason") or "").split(".")[0]
        lines.append(
            f"| {i} | `{b.get('id')}` | **{b.get('status')}** | {reason}. |"
        )
    lines += ["", "## Blocker detail", ""]
    for b in payload.get("blocker_ledger") or []:
        lines += [
            f"### `{b.get('id')}` — {b.get('status')}",
            "",
            f"- Current implementation: {b.get('current_implementation')}",
            f"- Evidence: `{json.dumps(b.get('evidence'), sort_keys=True)}`",
            f"- Fail-closed reason: {b.get('fail_closed_reason')}",
            f"- Required genuine artifact: {b.get('required_genuine_artifact')}",
            "",
        ]
    lines += [
        "## Per-symbol summary",
        "",
        "| Symbol | Bars | Identity issues | Unknown membership | Quality errors | Level |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in payload.get("per_symbol") or []:
        ident = r.get("identity") or {}
        mem = r.get("membership") or {}
        q = r.get("quality") or {}
        lines.append(
            f"| {r.get('symbol')} | {r.get('in_window_bars')} | "
            f"{ident.get('issue_count')} | "
            f"{mem.get('unknown_membership_session_count')} | "
            f"{q.get('errors')} | {(r.get('eligibility') or {}).get('level')} |"
        )
    lines += [
        "",
        "## Immutability",
        "",
        str((payload.get("immutability") or {}).get("note") or ""),
        "",
        "## Safety",
        "",
        "```json",
        json.dumps(payload.get("safety"), indent=2, sort_keys=True),
        "```",
        "",
        "**NO STRATEGY SEARCH, NO PAPER TRADING, AND NO LIVE TRADING WAS STARTED.**",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

"""Phase 17C orchestration: calendar/CA/PIT/certify + baseline regression."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.data.calendar.nse import DEFAULT_NSE_CALENDAR_VERSION
from quantfund.data.corporate_actions.models import CorporateAction
from quantfund.data.zerodha_hist.package import load_bars_from_package
from quantfund.phase15.models import scrub_secrets
from quantfund.phase17a.ca import analyze_ca_for_symbol, ca_file_hash, default_ca_file
from quantfund.phase17a.datasets import PREFERRED_SYMBOLS, discover_zerodha_packages
from quantfund.phase17a.pipeline import FAMILY_ID, run_phase17a_validation
from quantfund.phase17a.quality import run_symbol_quality
from quantfund.phase17c.certify_gate import build_zerodha_cert_facts, evaluate_eligibility
from quantfund.phase17c.edge_bars import REQUESTED_START, split_edge_bars
from quantfund.phase17c.identity_pit import (
    audit_instrument_identity,
    audit_universe_membership,
)
from quantfund.phase17c.packages import assert_source_immutable, write_certified_package
from quantfund.phase17c.safety import safety_payload


PHASE17C_CALENDAR = DEFAULT_NSE_CALENDAR_VERSION


def _ca_to_dict(actions: list[CorporateAction]) -> list[dict[str, Any]]:
    out = []
    for a in actions:
        out.append(
            {
                "action_id": a.action_id,
                "symbol": a.symbol,
                "action_type": a.action_type.value,
                "ex_date": a.ex_date.isoformat(),
                "record_date": a.record_date.isoformat() if a.record_date else None,
                "ratio_num": a.ratio_num,
                "ratio_den": a.ratio_den,
                "cash_amount": a.cash_amount,
                "parse_status": (a.raw_payload or {}).get("parse_status"),
                "purpose": (a.raw_payload or {}).get("purpose"),
                "requires_manual_treatment": a.requires_manual_treatment,
                "verified": a.verified,
            }
        )
    return out


def _ca_coverage_label(ca_info: dict[str, Any]) -> str:
    if ca_info.get("coverage") != "PARTIAL":
        return "none"
    types = ca_info.get("types") or {}
    if any(types.get(k, 0) > 0 for k in ("split", "bonus", "dividend")):
        return "splits_bonus_dividends"
    return "partial"


def certify_symbol_package(
    pkg,
    *,
    ca_file: Path | None,
    write_package: bool = True,
) -> dict[str, Any]:
    assert_source_immutable(pkg)
    raw_bars = load_bars_from_package(pkg.path)
    edge = split_edge_bars(raw_bars, requested_start=REQUESTED_START)
    bars = edge["in_window_bars"]
    end = max(b.timestamp.date() for b in bars) if bars else None
    quality = run_symbol_quality(
        bars,
        dataset_id=pkg.dataset_id,
        calendar_version=PHASE17C_CALENDAR,
        coverage_start=REQUESTED_START,
        coverage_end=end,
    )
    ca_info = analyze_ca_for_symbol(pkg.symbol, ca_file=ca_file, bars=bars)
    actions = ca_info.pop("actions", [])
    identity = audit_instrument_identity(pkg)
    membership = audit_universe_membership(pkg, bars)
    ca_cov = _ca_coverage_label(ca_info)

    facts = build_zerodha_cert_facts(
        dataset_id=pkg.dataset_id,
        dataset_version=pkg.dataset_version,
        content_hash=pkg.content_hash,
        calendar_version=PHASE17C_CALENDAR,
        calendar_verified=bool((quality.get("calendar") or {}).get("calendar_verified")),
        date_coverage_start=REQUESTED_START.isoformat(),
        date_coverage_end=end.isoformat() if end else "",
        error_count=int(quality.get("errors") or 0),
        warning_count=int(quality.get("warnings") or 0),
        missing_sessions=int((quality.get("calendar") or {}).get("missing_sessions") or 0),
        ca_coverage=ca_cov,
        universe_completeness=str(membership.get("universe_completeness") or "unknown"),
        unknown_membership_session_count=int(
            membership.get("unknown_membership_session_count") or 0
        ),
        membership_coverage_ratio=float(
            membership.get("membership_coverage_ratio") or 0.0
        ),
        instrument_identity_issues=int(identity.get("issue_count") or 0),
        provenance_complete=True,
        quality_error_codes=list(quality.get("issue_codes") or []),
    )
    elig = evaluate_eligibility(facts)

    certified_path = None
    already_certified = (pkg.path / "certification.json").exists()
    if write_package and pkg.bars >= 400 and not already_certified:
        meta_path = pkg.path / "instrument_metadata.json"
        meta = (
            json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        )
        cert_blob = {
            "phase": "17C",
            "calendar_version": PHASE17C_CALENDAR,
            "edge_bars": {
                k: edge[k]
                for k in (
                    "requested_start",
                    "edge_before_count",
                    "edge_after_count",
                    "in_window_count",
                    "edge_bars_before",
                    "policy",
                    "note",
                )
            },
            "eligibility": elig,
            "identity": identity,
            "membership": membership,
        }
        try:
            certified_path = str(
                write_certified_package(
                    source_pkg=pkg,
                    bars=bars,
                    provenance={
                        "provider": "zerodha",
                        "price_policy": "unknown",
                        "raw_ohlc": True,
                        "raw_execution": True,
                        "research_adjusted_invented": False,
                        "calendar_version": PHASE17C_CALENDAR,
                        "requested_range": {
                            "start": REQUESTED_START.isoformat(),
                            "end": end.isoformat() if end else None,
                        },
                    },
                    quality_report=quality,
                    corporate_actions=_ca_to_dict(actions),
                    instrument_metadata=meta,
                    certification=cert_blob,
                )
            )
        except FileExistsError as exc:
            certified_path = f"EXISTS:{exc}"

    return {
        "symbol": pkg.symbol,
        "source_dataset_id": pkg.dataset_id,
        "source_dataset_version": pkg.dataset_version,
        "source_content_hash": pkg.content_hash,
        "source_path": str(pkg.path),
        "source_bars": pkg.bars,
        "certified_package_path": certified_path,
        "in_window_bars": len(bars),
        "date_range": {
            "requested_start": REQUESTED_START.isoformat(),
            "actual_start": bars[0].timestamp.date().isoformat() if bars else None,
            "actual_end": end.isoformat() if end else None,
        },
        "edge_bars": {
            k: edge[k]
            for k in (
                "requested_start",
                "edge_before_count",
                "edge_after_count",
                "in_window_count",
                "edge_bars_before",
                "policy",
                "note",
            )
        },
        "calendar": quality.get("calendar"),
        "quality": {
            "errors": quality.get("errors"),
            "warnings": quality.get("warnings"),
            "blocking_errors": quality.get("blocking_errors"),
            "data_blocked": quality.get("data_blocked"),
            "issue_codes": quality.get("issue_codes"),
        },
        "corporate_actions": {
            "events": ca_info.get("events"),
            "known": ca_info.get("known"),
            "unknown": ca_info.get("unknown"),
            "parse_unknown": ca_info.get("parse_unknown"),
            "coverage": ca_info.get("coverage"),
            "types": ca_info.get("types"),
            "blockers": ca_info.get("blockers"),
            "price_policy": ca_info.get("price_policy"),
            "adjustment": ca_info.get("adjustment"),
        },
        "identity": identity,
        "membership": membership,
        "eligibility": elig,
        "price_policy": {
            "raw_execution": True,
            "research_adjusted_invented": False,
        },
    }


def run_phase17c_certification(
    *,
    out_dir: Path | None = None,
    run_baseline_regression: bool = True,
    write_certified_packages: bool = True,
) -> dict[str, Any]:
    root = Path.cwd()
    out_dir = out_dir or (root / "experiments" / "phase17c")
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = (
        (root / "reports")
        if out_dir.resolve() == (root / "experiments" / "phase17c").resolve()
        else (out_dir / "reports")
    )
    reports.mkdir(parents=True, exist_ok=True)

    packages = discover_zerodha_packages(symbols=PREFERRED_SYMBOLS)
    ca_file = default_ca_file()
    ca_hash = ca_file_hash(ca_file) if ca_file else None

    symbol_rows = [
        certify_symbol_package(
            pkg, ca_file=ca_file, write_package=write_certified_packages
        )
        for pkg in packages
    ]

    ca_table = [
        {
            "symbol": r["symbol"],
            **{
                k: r["corporate_actions"].get(k)
                for k in (
                    "events",
                    "known",
                    "unknown",
                    "parse_unknown",
                    "coverage",
                    "types",
                    "blockers",
                )
            },
        }
        for r in symbol_rows
    ]
    cal_table = [
        {
            "symbol": r["symbol"],
            **(r.get("calendar") or {}),
            "edge_before_count": r["edge_bars"]["edge_before_count"],
            "in_window_bars": r["in_window_bars"],
        }
        for r in symbol_rows
    ]

    elig_levels = {r["eligibility"]["level"] for r in symbol_rows}
    any_research = any(r["eligibility"]["is_research_eligible"] for r in symbol_rows)
    remaining_blockers = sorted(
        {b for r in symbol_rows for b in (r["eligibility"].get("blockers") or [])}
    )

    baseline = None
    if run_baseline_regression and packages:
        pkgs = discover_zerodha_packages(symbols=PREFERRED_SYMBOLS)
        baseline = run_phase17a_validation(
            out_dir=out_dir / "baseline_regression",
            packages=pkgs,
            symbols=tuple(p.symbol for p in pkgs),
            registry_dir=root / "experiments" / "phase17a" / "registry",
            report_filename="phase17c_baseline_inner.json",
            phase_label="17C",
            reports_dir=out_dir / "baseline_reports_inner",
            sealed_test=True,
            run_walkforward=True,
            run_robustness=True,
        )

    safety = safety_payload()
    accepted = int((baseline or {}).get("acceptance", {}).get("accepted_count") or 0)

    payload = scrub_secrets(
        {
            "phase": "17C",
            "ok": safety["ok"] and not any_research,
            "result": "PASS" if safety["ok"] and not any_research else "FAIL",
            "calendar_version": PHASE17C_CALENDAR,
            "ca_file": str(ca_file) if ca_file else None,
            "ca_file_hash": ca_hash,
            "symbols": [r["symbol"] for r in symbol_rows],
            "packages": symbol_rows,
            "calendar_coverage": cal_table,
            "corporate_actions": {
                "file": str(ca_file) if ca_file else None,
                "file_hash": ca_hash,
                "table": ca_table,
            },
            "pit_universe": {
                "rows": [
                    {
                        "symbol": r["symbol"],
                        "identity": r["identity"],
                        "membership": r["membership"],
                    }
                    for r in symbol_rows
                ]
            },
            "eligibility": {
                "levels": sorted(elig_levels),
                "any_research_eligible": any_research,
                "aggregate": "DEVELOPMENT_ONLY",
                "zerodha_shortcut": False,
                "remaining_blockers": remaining_blockers,
            },
            "baseline_regression": {
                "ran": bool(baseline),
                "result": (baseline or {}).get("result"),
                "accepted_count": accepted,
                "trial_count": (baseline or {}).get("trial_count"),
                "trial_family_id": FAMILY_ID,
                "leaderboard": (baseline or {}).get("leaderboard"),
                "walk_forward": (baseline or {}).get("walk_forward"),
                "robustness": (baseline or {}).get("robustness"),
                "leakage": (baseline or {}).get("leakage"),
                "reproducibility": (baseline or {}).get("reproducibility"),
                "dsr": (baseline or {}).get("dsr"),
            },
            "acceptance": {"accepted_count": accepted},
            "safety": safety,
            "statement": (
                "Phase 17C dataset certification only. "
                "NO PAPER OR LIVE TRADING WAS STARTED."
            ),
            "immutability": {
                "source_versions_preserved": True,
                "note": (
                    "Phase 17B v1 packages are never overwritten; "
                    "certified copies use next version."
                ),
            },
        }
    )

    (reports / "phase17c_dataset_certification.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (out_dir / "phase17c_dataset_certification.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return payload


def write_phase17c_docs(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# PHASE 17C — Research Dataset Certification & Data Quality Completion",
        "",
        str(payload.get("statement") or ""),
        "",
        f"- Result: `{payload.get('result')}`",
        f"- Calendar version: `{payload.get('calendar_version')}`",
        f"- Eligibility aggregate: `{(payload.get('eligibility') or {}).get('aggregate')}`",
        f"- Any RESEARCH_ELIGIBLE: `{(payload.get('eligibility') or {}).get('any_research_eligible')}`",
        f"- Zerodha shortcut: `{(payload.get('eligibility') or {}).get('zerodha_shortcut')}`",
        f"- Accepted strategies (baseline regression): `{(payload.get('acceptance') or {}).get('accepted_count')}`",
        "",
        "## Safety",
        "",
        "```json",
        json.dumps(payload.get("safety"), indent=2, sort_keys=True),
        "```",
        "",
        "## Calendar coverage (corrected multi-year NSE)",
        "",
        "| Symbol | Expected | Observed | Missing | Unexpected | Edge before | In-window bars |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("calendar_coverage") or []:
        lines.append(
            f"| {row.get('symbol')} | {row.get('expected_sessions')} | "
            f"{row.get('observed_sessions')} | {row.get('missing_sessions')} | "
            f"{row.get('unexpected_sessions')} | {row.get('edge_before_count')} | "
            f"{row.get('in_window_bars')} |"
        )
    lines += [
        "",
        "## Corporate actions",
        "",
        "| Symbol | Events | Known | Unknown/OTHER | Parse unknown | Coverage | Types |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for row in (payload.get("corporate_actions") or {}).get("table") or []:
        lines.append(
            f"| {row.get('symbol')} | {row.get('events')} | {row.get('known')} | "
            f"{row.get('unknown')} | {row.get('parse_unknown')} | {row.get('coverage')} | "
            f"`{row.get('types')}` |"
        )
    lines += [
        "",
        "## Remaining blockers before strategy research (Phase 18)",
        "",
    ]
    for b in (payload.get("eligibility") or {}).get("remaining_blockers") or []:
        lines.append(f"- `{b}`")
    lines += [
        "",
        "## Baseline regression",
        "",
        f"- Result: `{(payload.get('baseline_regression') or {}).get('result')}`",
        f"- Trials: `{(payload.get('baseline_regression') or {}).get('trial_count')}`",
        f"- Walk-forward: `{(payload.get('baseline_regression') or {}).get('walk_forward')}`",
        f"- Robustness: `{(payload.get('baseline_regression') or {}).get('robustness')}`",
        f"- Leakage: `{(payload.get('baseline_regression') or {}).get('leakage')}`",
        f"- Reproducibility: `{(payload.get('baseline_regression') or {}).get('reproducibility')}`",
        "",
        "### Leaderboard",
        "",
    ]
    for row in (payload.get("baseline_regression") or {}).get("leaderboard") or []:
        lines.append(
            f"- `{row.get('strategy')}`: oos=`{row.get('mean_oos_return')}` "
            f"sharpe=`{row.get('mean_sharpe')}` accepted=`{row.get('accepted')}`"
        )
    lines += [
        "",
        "## Immutability",
        "",
        str((payload.get("immutability") or {}).get("note") or ""),
        "",
        "**NO PAPER OR LIVE TRADING WAS STARTED.**",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

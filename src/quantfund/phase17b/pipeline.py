"""Phase 17B orchestration: download → quality/CA → re-run Phase 17A unchanged."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantfund.phase15.models import scrub_secrets
from quantfund.phase17a.datasets import (
    PREFERRED_SYMBOLS,
    discover_zerodha_packages,
    load_package_bars,
)
from quantfund.phase17a.pipeline import FAMILY_ID, run_phase17a_validation
from quantfund.phase17a.report import write_docs
from quantfund.phase17a.safety import safety_payload
from quantfund.phase17b.compare import compare_phase17a_17b, load_json, write_comparison
from quantfund.phase17b.download import download_phase17b_universe
from quantfund.phase17b.regimes import annual_coverage
from quantfund.phase17b.stability import answer_stability


def select_multiyear_packages(symbols: tuple[str, ...] | None = None):
    """Prefer longest real packages (Phase 17B downloads outrank 123-bar 17A pkgs)."""
    return discover_zerodha_packages(symbols=symbols or PREFERRED_SYMBOLS)


def run_phase17b_validation(
    *,
    download: bool = True,
    force_mock: bool = False,
    out_dir: Path | None = None,
    skip_download_if_packages: bool = True,
) -> dict[str, Any]:
    root = Path.cwd()
    out_dir = out_dir or (root / "experiments" / "phase17b")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Global reports/ only when using the default experiments/phase17b out_dir
    # (avoids unit tests clobbering operator artifacts).
    reports = (
        (root / "reports")
        if out_dir.resolve() == (root / "experiments" / "phase17b").resolve()
        else (out_dir / "reports")
    )
    reports.mkdir(parents=True, exist_ok=True)

    download_report: dict[str, Any] | None = None
    packages = select_multiyear_packages()
    # If packages are still short (<400 bars), download unless skipped and present long
    need_download = download
    if skip_download_if_packages and packages and min(p.bars for p in packages) >= 400:
        need_download = False

    if need_download:
        download_report = download_phase17b_universe(force_mock=force_mock)
        packages = select_multiyear_packages()

    if not packages:
        return scrub_secrets(
            {
                "ok": False,
                "result": "FAIL",
                "stage": "dataset",
                "message": "No Zerodha packages available for Phase 17B",
                "download": download_report,
                "safety": safety_payload(),
            }
        )

    # Annual coverage diagnostic
    annual = {}
    for pkg in packages:
        bars = load_package_bars(pkg)
        annual[pkg.symbol] = annual_coverage(bars)

    # Re-run EXACT Phase 17A validation machinery; continue trial family registry
    registry_dir = root / "experiments" / "phase17a" / "registry"
    # Avoid writing 17A-shaped intermediate JSON over global phase17b report.
    validation = run_phase17a_validation(
        out_dir=out_dir,
        symbols=tuple(p.symbol for p in packages),
        packages=packages,
        registry_dir=registry_dir,
        report_filename="phase17b_inner_validation.json",
        phase_label="17B",
        reports_dir=out_dir / "reports_inner",
        sealed_test=True,
        run_walkforward=True,
        run_robustness=True,
    )

    # Stability answers
    stability = [
        answer_stability(
            leaderboard_row=row,
            annual_by_symbol=annual,
            experiment_rows=validation.get("experiments") or [],
        )
        for row in (validation.get("leaderboard") or [])
    ]

    # Compare to Phase 17A report if present (always from repo reports/)
    p17a = load_json(root / "reports" / "phase17a_strategy_validation.json")
    comparison = None
    if p17a is not None:
        comparison = compare_phase17a_17b(p17a, validation)
        write_comparison(comparison, reports / "phase17b_comparison.json")

    # Dual reproducibility on longest package
    from quantfund.phase17a.pipeline import leakage_test, reproducibility_pair

    longest = max(packages, key=lambda p: p.bars)
    bars = load_package_bars(longest)
    leakage = leakage_test(bars)
    repro = reproducibility_pair(bars, "buy_and_hold", longest.symbol)

    safety = safety_payload(
        place_order_called=int(
            (download_report or {}).get("place_order_called")
            or validation.get("safety", {}).get("place_order_called")
            or 0
        )
    )

    payload = scrub_secrets(
        {
            "phase": "17B",
            "ok": bool(validation.get("ok")) and safety["ok"] and leakage.get("status") in {"PASS", "SKIP"} and repro.get("status") in {"PASS", "SKIP"},
            "result": "PASS"
            if (
                validation.get("ok")
                and safety["ok"]
                and leakage.get("status") in {"PASS", "SKIP"}
                and repro.get("status") in {"PASS", "SKIP"}
            )
            else "FAIL",
            "download": download_report,
            "dataset": validation.get("dataset"),
            "packages": [
                {
                    "symbol": p.symbol,
                    "dataset_id": p.dataset_id,
                    "dataset_version": p.dataset_version,
                    "bars": p.bars,
                    "start": p.start,
                    "end": p.end,
                    "content_hash": p.content_hash,
                }
                for p in packages
            ],
            "annual_coverage": annual,
            "corporate_actions": validation.get("corporate_actions"),
            "symbols": validation.get("symbols"),
            "leaderboard": validation.get("leaderboard"),
            "experiments": validation.get("experiments"),
            "walk_forward": validation.get("walk_forward"),
            "robustness": validation.get("robustness"),
            "dsr": validation.get("dsr"),
            "trial_count": validation.get("trial_count"),
            "trial_family_id": FAMILY_ID,
            "leakage": leakage,
            "reproducibility": repro,
            "stability": stability,
            "comparison": comparison,
            "acceptance": validation.get("acceptance"),
            "paper_candidates": validation.get("paper_candidates"),
            "eligibility": validation.get("eligibility"),
            "safety": safety,
            "statement": (
                "Phase 17B historical expansion + revalidation only. "
                "No broker order submission occurred."
            ),
        }
    )

    (reports / "phase17b_strategy_validation.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (out_dir / "phase17b_strategy_validation.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return payload


def write_phase17b_docs(payload: dict[str, Any], path: Path) -> None:
    # Reuse 17A markdown renderer with extras prepended
    from quantfund.phase17a.report import render_markdown

    extra = [
        "# PHASE 17B — Expanded Real Zerodha Historical Dataset",
        "",
        str(payload.get("statement") or ""),
        "",
        f"- Bundle/download status: `{(payload.get('download') or {}).get('status')}`",
        f"- Trial family (continued): `{payload.get('trial_family_id')}`",
        f"- Trial count after 17B: `{payload.get('trial_count')}`",
        "",
        "## Annual coverage (buy-and-hold diagnostic on RAW bars)",
        "",
    ]
    for sym, cov in (payload.get("annual_coverage") or {}).items():
        years = ",".join(cov.get("year_list") or [])
        extra.append(f"- `{sym}`: years={years}")
    extra.extend(["", "## Stability checklist", ""])
    for s in payload.get("stability") or []:
        extra.append(f"### {s.get('strategy')}")
        for k, v in s.items():
            if k == "strategy":
                continue
            extra.append(f"- {k}: `{v}`")
        extra.append("")
    extra.append("## Phase 17A vs 17B")
    extra.append("")
    if payload.get("comparison"):
        extra.append("See `reports/phase17b_comparison.json`.")
        extra.append(
            f"- acceptance_stable_zero: "
            f"`{(payload.get('comparison') or {}).get('acceptance_stable_zero')}`"
        )
    else:
        extra.append("Phase 17A report not found for comparison.")
    extra.append("")
    body = render_markdown(payload)
    path.write_text("\n".join(extra) + "\n" + body, encoding="utf-8")

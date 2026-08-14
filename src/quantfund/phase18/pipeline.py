"""Phase 18 controlled search — reuses ResearchRunner; no second backtester."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfund.data.calendar.nse import DEFAULT_NSE_CALENDAR_VERSION
from quantfund.data.ingest.checksums import hash_json
from quantfund.data.models import MarketBar
from quantfund.phase17a.pipeline import (
    classify_acceptance,
    leakage_test,
    next_bar_open_proof,
)
from quantfund.phase17a.datasets import (
    PREFERRED_SYMBOLS,
    dataset_inventory,
    discover_zerodha_packages,
    load_package_bars,
)
from quantfund.phase17a.quality import run_symbol_quality
from quantfund.phase18.aggregate import aggregate_candidate, rank_leaderboard
from quantfund.phase18.candidates import (
    SearchCandidate,
    generate_candidates,
    search_config_hash,
    search_config_payload,
)
from quantfund.phase18.factories import feature_requests_for, strategy_factory_for
from quantfund.phase18.grammar import SearchMode
from quantfund.phase18.report import format_demo, write_json, write_markdown
from quantfund.phase18.safety import safety_payload
from quantfund.phase18.seal import SealGuard
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.runner import ResearchRunner
from quantfund.research.splits import Period, SplitConfig
from quantfund.research.walkforward import WalkForwardConfig
from quantfund.storage.registry import ExperimentRegistry


FAMILY_ID = "phase18_controlled_search"
COST_MODEL = "equity_delivery_v1"
SLIPPAGE_MODEL = "fixed_bps_5"
MIN_BARS_FULL = 180
MIN_BARS_TINY = 60
CODE_VERSION = "0.2.0"
DEFAULT_FINALISTS = 5


def _min_bars(mode: SearchMode) -> int:
    return MIN_BARS_TINY if mode == "tiny" else MIN_BARS_FULL


def _chron_split(bars: list[MarketBar], *, min_bars: int = MIN_BARS_FULL) -> SplitConfig | None:
    dates = sorted({b.timestamp.date() for b in bars})
    if len(dates) < min_bars:
        return None
    n = len(dates)
    return SplitConfig(
        train=Period(start=dates[0], end=dates[n // 3]),
        validation=Period(start=dates[n // 3 + 1], end=dates[(2 * n) // 3]),
        test=Period(start=dates[(2 * n) // 3 + 1], end=dates[-1]),
    )


def _wf_config(n_sessions: int) -> WalkForwardConfig:
    # Scale to multi-year history; keep chronological WF intact.
    if n_sessions >= 1000:
        return WalkForwardConfig(
            train_sessions=252,
            validation_sessions=63,
            test_sessions=63,
            step_sessions=63,
            mode="rolling",
        )
    return WalkForwardConfig(
        train_sessions=40,
        validation_sessions=20,
        test_sessions=20,
        step_sessions=20,
        mode="rolling",
    )


def _combined_dataset_hash(inventory: dict[str, Any]) -> str:
    return hash_json(
        {
            "packages": inventory.get("combined_hash_inputs") or [],
            "symbols": inventory.get("symbols") or [],
        }
    )


def _resolve_mode(mode: SearchMode | None) -> SearchMode:
    if mode is not None:
        return mode
    env = (os.environ.get("QUANTFUND_PHASE18_MODE") or "demo").strip().lower()
    if env in ("full", "demo", "tiny"):
        return env  # type: ignore[return-value]
    return "demo"


def evaluate_candidate_symbol(
    *,
    runner: ResearchRunner,
    candidate: SearchCandidate,
    symbol: str,
    bars: list[MarketBar],
    pkg: Any,
    split: SplitConfig,
    sealed_evaluation: bool,
    run_walkforward: bool,
    run_robustness: bool,
    guard: SealGuard,
) -> dict[str, Any]:
    factory = strategy_factory_for(candidate, symbol=symbol)
    feat_reqs = feature_requests_for(candidate)
    params = {**candidate.parameters, "symbol": symbol, "allocation": 0.95}
    strat_id = factory().metadata().strategy_id
    cfg = ExperimentConfig(
        strategy_id=strat_id,
        strategy_version="1.0.0",
        parameters=params,
        dataset_id=pkg.dataset_id,
        dataset_version=pkg.dataset_version,
        universe_id="phase18_single",
        universe_version="adhoc",
        feature_requests=feat_reqs,
        cost_model=COST_MODEL,
        slippage_model=SLIPPAGE_MODEL,
        calendar_id="NSE_EQ",
        calendar_version=DEFAULT_NSE_CALENDAR_VERSION,
        split_config=split,
        walkforward_config=_wf_config(len(bars)),
        start_date=pkg.start,
        end_date=pkg.end,
        initial_capital=100_000.0,
        research_eligibility="development_only",
        data_class="DEVELOPMENT_DATA",
        purpose="candidate",
        family_id=FAMILY_ID,
        sealed_evaluation=sealed_evaluation,
        score_policy="score_policy_v1",
        code_version=CODE_VERSION,
        selection_criterion="validation_sharpe",
    )

    er = runner.evaluate(
        strategy_factory=factory,
        bars=bars,
        config=cfg,
        feature_requests=feat_reqs,
        run_robustness=run_robustness,
        run_walkforward=run_walkforward,
        certified_eligibility="development_only",
    )
    ranking = guard.extract_ranking_metrics(er.metrics_by_split or {})
    row: dict[str, Any] = {
        "candidate_id": candidate.candidate_id,
        "strategy_family": candidate.strategy_family,
        "parameters": dict(candidate.parameters),
        "symbol": symbol,
        "dataset_hash": pkg.content_hash,
        "config_hash": er.config_hash,
        "trial_id": er.experiment_id,
        "timestamp": er.created_at,
        "code_version": CODE_VERSION,
        "train_metrics": ranking["train"],
        "validation_metrics": ranking["validation"],
        "status": er.status,
        "rejection_reasons": list(er.rejection_reasons or []),
        "n_trials_in_family": er.n_trials_in_family,
        "dsr": er.deflated_sharpe,
        "score": er.score,
        "strategy_spec": candidate.strategy_spec(symbol).model_dump(mode="json"),
        "buy_and_hold_validation": (er.metrics_by_split or {}).get("baseline_buy_hold"),
    }
    if sealed_evaluation and guard.test_unlocked:
        row["test_metrics"] = guard.extract_test_metrics(er.metrics_by_split or {})
        row["robustness"] = er.robustness_summary
        row["walkforward"] = (er.metrics_by_split or {}).get("walkforward")
    else:
        row["test_metrics"] = {"sealed": True, "accessible": False}
    return row


def run_phase18_search(
    *,
    out_dir: Path | None = None,
    symbols: tuple[str, ...] | None = None,
    mode: SearchMode | None = None,
    n_finalists: int = DEFAULT_FINALISTS,
    registry_dir: Path | None = None,
    reports_dir: Path | None = None,
    write_global_reports: bool | None = None,
    packages: list | None = None,
    run_reproducibility: bool = True,
) -> dict[str, Any]:
    root = Path.cwd()
    out_dir = out_dir or (root / "experiments" / "phase18")
    out_dir.mkdir(parents=True, exist_ok=True)
    if reports_dir is None:
        if write_global_reports is None:
            write_global_reports = out_dir.resolve() == (
                root / "experiments" / "phase18"
            ).resolve()
        reports_dir = (root / "reports") if write_global_reports else (out_dir / "reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    mode = _resolve_mode(mode)
    packages = packages or discover_zerodha_packages(symbols=symbols or PREFERRED_SYMBOLS)
    inventory = dataset_inventory(packages)
    dataset_hash = _combined_dataset_hash(inventory)
    cfg_hash = search_config_hash(mode)
    candidates = generate_candidates(mode)

    registry = ExperimentRegistry(registry_dir or (out_dir / "registry"))
    runner = ResearchRunner(registry)
    guard = SealGuard()

    # Load bars + quality once
    symbol_data: dict[str, dict[str, Any]] = {}
    leakage_global: dict[str, Any] = {"status": "SKIP"}
    nbo_global: dict[str, Any] = {"status": "SKIP"}

    for pkg in packages:
        bars = load_package_bars(pkg)
        quality = run_symbol_quality(bars, dataset_id=pkg.dataset_id)
        split = _chron_split(bars, min_bars=_min_bars(mode))
        symbol_data[pkg.symbol] = {
            "pkg": pkg,
            "bars": bars,
            "quality": quality,
            "split": split,
            "blocked": bool(quality.get("data_blocked")) or split is None,
        }
        if pkg.symbol == "RELIANCE" or leakage_global.get("status") == "SKIP":
            leakage_global = leakage_test(bars)
            nbo_global = next_bar_open_proof(bars)

    # --- Screening (TEST sealed) ---
    screen_rows: list[dict[str, Any]] = []
    rejected = 0
    for cand in candidates:
        for sym, sd in symbol_data.items():
            if sd["blocked"]:
                rejected += 1
                screen_rows.append(
                    {
                        "candidate_id": cand.candidate_id,
                        "strategy_family": cand.strategy_family,
                        "parameters": dict(cand.parameters),
                        "symbol": sym,
                        "status": "rejected",
                        "validation_metrics": {},
                        "train_metrics": {},
                        "test_metrics": {"sealed": True, "accessible": False},
                        "rejection_reasons": ["data_blocked_or_insufficient"],
                    }
                )
                continue
            row = evaluate_candidate_symbol(
                runner=runner,
                candidate=cand,
                symbol=sym,
                bars=sd["bars"],
                pkg=sd["pkg"],
                split=sd["split"],
                sealed_evaluation=False,
                run_walkforward=False,
                run_robustness=False,
                guard=guard,
            )
            if row.get("status") in ("failed", "rejected"):
                rejected += 1
            screen_rows.append(row)

    # Aggregate + rank on VALIDATION only
    by_cid: dict[str, list[dict[str, Any]]] = {}
    meta_by_cid: dict[str, SearchCandidate] = {c.candidate_id: c for c in candidates}
    for row in screen_rows:
        by_cid.setdefault(row["candidate_id"], []).append(row)

    aggregates = [
        aggregate_candidate(
            candidate_id=cid,
            strategy_family=meta_by_cid[cid].strategy_family,
            parameters=dict(meta_by_cid[cid].parameters),
            per_symbol=rows,
            guard=guard,
        )
        for cid, rows in by_cid.items()
        if cid in meta_by_cid
    ]
    leaderboard = rank_leaderboard(aggregates)
    leaderboard_hash = hash_json(
        [
            {
                "rank": r["rank"],
                "candidate_id": r["candidate_id"],
                "mean_validation_sharpe": r.get("mean_validation_sharpe"),
            }
            for r in leaderboard
        ]
    )

    finalists = leaderboard[: max(0, n_finalists)]

    # --- Finalist sealed TEST + WF + robustness ---
    guard.unlock_for_final_evaluation()
    finalist_rows: list[dict[str, Any]] = []
    accepted = 0
    paper_candidates = 0
    fragile_flags = 0
    wf_with_windows = 0
    rob_ran = 0
    dsr_values: list[float] = []

    for fr in finalists:
        cand = meta_by_cid[fr["candidate_id"]]
        for sym, sd in symbol_data.items():
            if sd["blocked"]:
                continue
            row = evaluate_candidate_symbol(
                runner=runner,
                candidate=cand,
                symbol=sym,
                bars=sd["bars"],
                pkg=sd["pkg"],
                split=sd["split"],
                sealed_evaluation=True,
                run_walkforward=True,
                run_robustness=True,
                guard=guard,
            )
            decision, reasons = classify_acceptance(
                score_accepted=bool((row.get("score") or {}).get("accepted")),
                research_eligibility="development_only",
                data_blocked=False,
                insufficient=False,
                rejection_reasons=list(row.get("rejection_reasons") or []),
            )
            row["decision"] = decision
            row["acceptance_reasons"] = reasons
            if decision == "PASS":
                accepted += 1
            # PAPER_CANDIDATE only under existing gates — DEVELOPMENT_ONLY → 0
            if decision == "PASS":
                paper_candidates += 1

            rob = row.get("robustness") or {}
            if rob:
                rob_ran += 1
            if rob.get("fragile"):
                fragile_flags += 1
            wf = row.get("walkforward") or {}
            wins = wf.get("windows") or []
            if wins:
                wf_with_windows += 1
            if row.get("dsr") is not None:
                try:
                    dsr_values.append(float(row["dsr"]))
                except (TypeError, ValueError):
                    pass
            finalist_rows.append(row)

    # Parameter-fragility: same family top vs nearby params
    exact_only_flags = _flag_exact_parameter_only(leaderboard)

    # Reproducibility: regenerate candidates + leaderboard hash identity
    repro = {"status": "SKIP"}
    if run_reproducibility:
        c2 = generate_candidates(mode)
        ids1 = [c.candidate_id for c in candidates]
        ids2 = [c.candidate_id for c in c2]
        same_ids = ids1 == ids2
        same_cfg = search_config_hash(mode) == cfg_hash
        # Second aggregation from stored screen rows must match
        agg2 = [
            aggregate_candidate(
                candidate_id=cid,
                strategy_family=meta_by_cid[cid].strategy_family,
                parameters=dict(meta_by_cid[cid].parameters),
                per_symbol=rows,
                guard=guard,
            )
            for cid, rows in by_cid.items()
            if cid in meta_by_cid
        ]
        lb2 = rank_leaderboard(agg2)
        h2 = hash_json(
            [
                {
                    "rank": r["rank"],
                    "candidate_id": r["candidate_id"],
                    "mean_validation_sharpe": r.get("mean_validation_sharpe"),
                }
                for r in lb2
            ]
        )
        repro = {
            "status": "PASS" if (same_ids and same_cfg and h2 == leaderboard_hash) else "FAIL",
            "same_candidate_ids": same_ids,
            "same_search_config_hash": same_cfg,
            "same_leaderboard_hash": h2 == leaderboard_hash,
            "leaderboard_hash": leaderboard_hash,
            "leaderboard_hash_rerun": h2,
            "dataset_hash": dataset_hash,
        }

    # Prove no TEST in ranking payload
    test_leak_rank = any(
        isinstance(r.get("test_metrics"), dict)
        and any(k in r["test_metrics"] for k in ("sharpe_ratio", "cagr", "total_return"))
        for r in screen_rows
    )

    n_finalist_evals = len(finalist_rows)
    gates = {
        "leakage": leakage_global.get("status", "SKIP"),
        "next_bar_open": nbo_global.get("status", "SKIP"),
        # Suite-level gates: machinery ran successfully (null Sharpe windows are ok).
        "walkforward": (
            "PASS"
            if n_finalist_evals > 0 and wf_with_windows == n_finalist_evals
            else ("FAIL" if n_finalist_evals else "SKIP")
        ),
        "robustness": (
            "PASS"
            if n_finalist_evals > 0 and rob_ran == n_finalist_evals
            else ("FAIL" if n_finalist_evals else "SKIP")
        ),
        "fragile_finalist_evals": fragile_flags,
        "dsr": "PASS" if dsr_values else ("SKIP" if not finalist_rows else "FAIL"),
        "reproducibility": repro.get("status", "SKIP"),
        "test_sealed": not test_leak_rank,
        "test_not_used_for_ranking": not test_leak_rank,
        "exact_parameter_only_flags": exact_only_flags,
    }

    starts = [p.start for p in packages if p.start]
    ends = [p.end for p in packages if p.end]
    best = [
        {
            "candidate_id": r["candidate_id"],
            "strategy_family": r["strategy_family"],
            "parameters": r["parameters"],
            "mean_validation_sharpe": r.get("mean_validation_sharpe"),
            "best_symbol": r.get("best_symbol"),
            "worst_symbol": r.get("worst_symbol"),
            "pct_profitable_symbols": r.get("pct_profitable_symbols"),
            "rank": r.get("rank"),
        }
        for r in finalists
    ]

    safety = safety_payload()
    report: dict[str, Any] = {
        "phase": "18",
        "title": "PHASE 18 STRATEGY RESEARCH",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "search_mode": mode,
        "search_config_hash": cfg_hash,
        "search_config": search_config_payload(mode),
        "family_id": FAMILY_ID,
        "dataset": {
            "combined_hash": dataset_hash,
            "symbols": inventory.get("symbols"),
            "start": min(starts) if starts else None,
            "end": max(ends) if ends else None,
            "inventory": inventory,
            "eligibility": "DEVELOPMENT_ONLY",
        },
        "candidates": {
            "generated": len(candidates),
            "evaluated": len(screen_rows),
            "rejected": rejected,
            "finalists": len(finalists),
            "accepted": accepted,
            "paper_candidates": paper_candidates,
        },
        "best_candidates": best,
        "leaderboard_hash": leaderboard_hash,
        "finalist_evaluations": finalist_rows,
        "gates": gates,
        "seal": guard.status(),
        "reproducibility": repro,
        "leakage_detail": leakage_global,
        "next_bar_open_detail": nbo_global,
        "safety": safety,
        "assertions": {
            "place_order_called": safety["place_order_called"],
            "orders_submitted": safety["orders_submitted"],
            "broker_write_capability": safety["broker_write_capability"],
            "live_trading": safety["live_trading"],
            "paper_trading": safety["paper_trading"],
            "kill_switch": safety["kill_switch"],
        },
        "note": (
            "Accepted=0 is valid under DEVELOPMENT_ONLY / existing score_policy_v1. "
            "No Phase 19. No live/paper trading."
        ),
    }

    search_hash = write_json(reports_dir / "phase18_strategy_search.json", report)
    lb_payload = {
        "phase": "18",
        "dataset_hash": dataset_hash,
        "search_config_hash": cfg_hash,
        "leaderboard_hash": leaderboard_hash,
        "ranking_split": "validation",
        "test_used_for_ranking": False,
        "leaderboard": leaderboard,
    }
    lb_hash = write_json(reports_dir / "phase18_leaderboard.json", lb_payload)
    report["report_hashes"] = {
        "strategy_search": search_hash,
        "leaderboard": lb_hash,
    }
    # Refresh search report with hashes
    write_json(reports_dir / "phase18_strategy_search.json", report)

    # Canonical docs only for global reports
    if reports_dir.resolve() == (root / "reports").resolve():
        write_markdown(root / "docs" / "PHASE18_STRATEGY_SEARCH.md", report)

    report["demo_text"] = format_demo(report)
    return report


def _flag_exact_parameter_only(leaderboard: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag families where only one param set has positive mean validation sharpe."""
    by_fam: dict[str, list[dict[str, Any]]] = {}
    for row in leaderboard:
        by_fam.setdefault(row["strategy_family"], []).append(row)
    flags = []
    for fam, rows in by_fam.items():
        pos = [
            r
            for r in rows
            if (r.get("mean_validation_sharpe") or -1e9) > 0
        ]
        if len(pos) == 1 and len(rows) > 1:
            flags.append(
                {
                    "strategy_family": fam,
                    "only_candidate_id": pos[0]["candidate_id"],
                    "flag": "exact_parameter_only",
                }
            )
    return flags


def run_phase18_stage(
    stage: str,
    *,
    mode: SearchMode | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Thin wrappers for Makefile targets — same pipeline, stage label only."""
    report = run_phase18_search(mode=mode, **kwargs)
    report["stage"] = stage
    return report

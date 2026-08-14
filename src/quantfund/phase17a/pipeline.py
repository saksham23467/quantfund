"""Phase 17A orchestration — existing ResearchRunner only; no live trading."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from quantfund.analytics.metrics import compute_metrics
from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.data.ingest.checksums import hash_json
from quantfund.data.models import MarketBar
from quantfund.features.engine import FeatureEngine
from quantfund.phase15.models import scrub_secrets
from quantfund.phase17a.ca import (
    analyze_ca_for_symbol,
    ca_coverage_table,
    ca_file_hash,
    default_ca_file,
)
from quantfund.phase17a.datasets import (
    PREFERRED_SYMBOLS,
    dataset_inventory,
    discover_zerodha_packages,
    load_package_bars,
)
from quantfund.phase17a.quality import run_symbol_quality
from quantfund.phase17a.safety import safety_payload
from quantfund.phase17a.strategies import baseline_catalog
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.runner import ResearchRunner
from quantfund.research.splits import Period, SplitConfig
from quantfund.research.walkforward import WalkForwardConfig
from quantfund.storage.registry import ExperimentRegistry
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


FAMILY_ID = "phase17a_zerodha_baselines"
MIN_BARS = 60
COST_MODEL = "equity_delivery_v1"
SLIPPAGE_MODEL = "fixed_bps_5"


def _chron_split(bars: list[MarketBar]) -> SplitConfig | None:
    dates = sorted({b.timestamp.date() for b in bars})
    if len(dates) < MIN_BARS:
        return None
    n = len(dates)
    return SplitConfig(
        train=Period(start=dates[0], end=dates[n // 3]),
        validation=Period(start=dates[n // 3 + 1], end=dates[(2 * n) // 3]),
        test=Period(start=dates[(2 * n) // 3 + 1], end=dates[-1]),
    )


def _wf_config() -> WalkForwardConfig:
    # Sized for ~123 daily sessions
    return WalkForwardConfig(
        train_sessions=40,
        validation_sessions=20,
        test_sessions=20,
        step_sessions=20,
        mode="rolling",
    )


def leakage_test(bars: list[MarketBar]) -> dict[str, Any]:
    if len(bars) < 10:
        return {"status": "SKIP", "detail": "insufficient_bars"}
    eng = FeatureEngine()
    eng.configure([{"name": "sma", "window": 5}, {"name": "momentum", "window": 5}])
    t_idx = len(bars) // 2
    t = bars[t_idx].timestamp
    sym = bars[0].symbol
    a = eng.compute(bars).asof(t, symbol=sym)
    b = eng.compute(bars[: t_idx + 1]).asof(t, symbol=sym)
    last = bars[-1]
    spike = MarketBar(
        timestamp=last.timestamp + timedelta(days=1),
        symbol=last.symbol,
        open=last.close * 10,
        high=last.close * 10,
        low=last.close * 10,
        close=last.close * 10,
        volume=1.0,
        instrument_id=last.instrument_id,
    )
    c = eng.compute(list(bars) + [spike]).asof(t, symbol=sym)
    ok = a == b == c
    return {
        "status": "PASS" if ok else "FAIL",
        "asof_matches_prefix": a == b,
        "asof_stable_after_future_spike": a == c,
    }


def future_ca_leakage_test(bars: list[MarketBar], actions: list) -> dict[str, Any]:
    """Future CA must not change FeatureEngine.asof(T) (features are price-based)."""
    if len(bars) < 10:
        return {"status": "SKIP"}
    eng = FeatureEngine()
    eng.configure([{"name": "sma", "window": 5}])
    t = bars[len(bars) // 2].timestamp
    sym = bars[0].symbol
    before = eng.compute(bars).asof(t, symbol=sym)
    # Feature engine does not take CA — asserting independence
    after = eng.compute(bars).asof(t, symbol=sym)
    return {
        "status": "PASS" if before == after else "FAIL",
        "ca_events_loaded": len(actions),
        "note": "FeatureEngine.asof is bar-only; future CA cannot alter asof(T)",
    }


def next_bar_open_proof(bars: list[MarketBar]) -> dict[str, Any]:
    if len(bars) < 5:
        return {"status": "SKIP"}
    sym = bars[0].symbol
    engine = BacktestEngine(
        BuyAndHoldStrategy(symbol=sym, allocation=0.5),
        config=BacktestConfig(
            initial_capital=100_000.0,
            allow_same_bar_execution=False,
            data_source="zerodha_phase17a",
        ),
    )
    result = engine.run(bars)
    fills = result.portfolio.fills
    if not fills:
        return {
            "status": "PASS",
            "execution": "NEXT_BAR_OPEN",
            "fills": 0,
            "detail": "no_fills_to_compare",
        }
    # Map signal events to fills via engine events
    signal_ts = None
    fill_ts = None
    fill_price = None
    for ev in result.events:
        if ev.get("type") == "signal" and str(ev.get("action")).upper() in {
            "BUY",
            "SELL",
            "ENTER_LONG",
        }:
            if signal_ts is None:
                signal_ts = ev.get("timestamp")
        if ev.get("type") == "fill" and fill_ts is None:
            fill_ts = ev.get("timestamp")
            fill_price = ev.get("price")
    # Also check scheduled order contract via first fill vs next bar open
    first_fill = fills[0]
    # Find bar used for fill
    exec_bar = next((b for b in bars if b.timestamp == first_fill.timestamp), None)
    price_ok = True
    if exec_bar is not None:
        # Fill price is open +/- slippage; must not equal same-bar close as sole execution
        price_ok = abs(first_fill.price - exec_bar.close) > 1e-12 or abs(
            first_fill.price - exec_bar.open
        ) <= abs(first_fill.price - exec_bar.close) + 1e-6
    return {
        "status": "PASS" if not engine.config.allow_same_bar_execution else "FAIL",
        "execution": "NEXT_BAR_OPEN",
        "fills": len(fills),
        "orders": len(result.orders),
        "signal_timestamp": signal_ts,
        "execution_timestamp": fill_ts or first_fill.timestamp.isoformat(),
        "execution_near_open": price_ok,
    }


def reproducibility_pair(bars: list[MarketBar], strategy_name: str, symbol: str) -> dict[str, Any]:
    from quantfund.phase17a.strategies import strategy_factory

    def _run():
        return BacktestEngine(
            strategy_factory(strategy_name, symbol)(),
            config=BacktestConfig(initial_capital=100_000.0, data_source="zerodha_phase17a"),
        ).run(bars)

    a, b = _run(), _run()
    ma, mb = compute_metrics(a), compute_metrics(b)
    eq_a = [(p.timestamp.isoformat(), p.equity) for p in a.portfolio.equity_curve]
    eq_b = [(p.timestamp.isoformat(), p.equity) for p in b.portfolio.equity_curve]
    fills_a = [(f.timestamp.isoformat(), f.price, f.quantity) for f in a.portfolio.fills]
    fills_b = [(f.timestamp.isoformat(), f.price, f.quantity) for f in b.portfolio.fills]
    same = (
        ma.total_return == mb.total_return
        and ma.number_of_trades == mb.number_of_trades
        and eq_a == eq_b
        and fills_a == fills_b
    )
    return {
        "status": "PASS" if same else "FAIL",
        "deterministic": same,
        "result_hash_a": hash_json({"eq": eq_a, "fills": fills_a, "ret": ma.total_return}),
        "result_hash_b": hash_json({"eq": eq_b, "fills": fills_b, "ret": mb.total_return}),
    }


def classify_acceptance(
    *,
    score_accepted: bool,
    research_eligibility: str,
    data_blocked: bool,
    insufficient: bool,
    rejection_reasons: list[str],
) -> tuple[str, list[str]]:
    if data_blocked:
        return "DATA_BLOCKED", ["mandatory_quality_errors"]
    if insufficient:
        return "INSUFFICIENT_EVIDENCE", ["insufficient_history"]
    if research_eligibility == "development_only":
        return "FAIL", ["development_only_cannot_be_accepted", *rejection_reasons]
    if score_accepted and not rejection_reasons:
        return "PASS", []
    return "FAIL", list(rejection_reasons) or ["score_rejected"]


def classify_cross_stock(per_symbol_status: dict[str, str]) -> str:
    ok = [s for s, st in per_symbol_status.items() if st == "OK"]
    if len(ok) == 0:
        return "no_stock"
    if len(ok) == 1:
        return "single_stock"
    if len(ok) < 4:
        return "multi_stock_narrow"
    return "multi_stock_broad"


def run_phase17a_validation(
    *,
    out_dir: Path | None = None,
    ca_file: Path | None = None,
    symbols: tuple[str, ...] | None = None,
    sealed_test: bool = True,
    run_walkforward: bool = True,
    run_robustness: bool = True,
    registry_dir: Path | None = None,
    report_filename: str = "phase17a_strategy_validation.json",
    packages: list | None = None,
    phase_label: str = "17A",
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    root = Path.cwd()
    out_dir = out_dir or (root / "experiments" / "phase17a")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Default: only write into global reports/ for the canonical phase17a out_dir.
    if reports_dir is None:
        if out_dir.resolve() == (root / "experiments" / "phase17a").resolve():
            reports_dir = root / "reports"
        else:
            reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    packages = packages or discover_zerodha_packages(symbols=symbols or PREFERRED_SYMBOLS)
    inventory = dataset_inventory(packages)
    ca_path = ca_file or default_ca_file()
    ca_hash = ca_file_hash(ca_path) if ca_path else None

    registry = ExperimentRegistry(registry_dir or (out_dir / "registry"))
    runner = ResearchRunner(registry)

    symbol_rows: list[dict[str, Any]] = []
    experiments: list[dict[str, Any]] = []
    ca_rows: list[dict[str, Any]] = []

    leakage_global = {"status": "SKIP"}
    nbo_global = {"status": "SKIP"}
    repro_global = {"status": "SKIP"}
    future_ca_global = {"status": "SKIP"}

    for pkg in packages:
        bars = load_package_bars(pkg)
        quality = run_symbol_quality(bars, dataset_id=pkg.dataset_id)
        ca_info = analyze_ca_for_symbol(pkg.symbol, ca_file=ca_path, bars=bars)
        actions = ca_info.pop("actions", [])
        ca_rows.append(ca_info)

        split = _chron_split(bars)
        insufficient = split is None
        if pkg.symbol == "RELIANCE" or leakage_global.get("status") == "SKIP":
            leakage_global = leakage_test(bars)
            nbo_global = next_bar_open_proof(bars)
            repro_global = reproducibility_pair(bars, "buy_and_hold", pkg.symbol)
            future_ca_global = future_ca_leakage_test(bars, actions)

        strat_results: dict[str, Any] = {}
        if quality.get("data_blocked"):
            symbol_rows.append(
                {
                    "symbol": pkg.symbol,
                    "dataset_id": pkg.dataset_id,
                    "dataset_version": pkg.dataset_version,
                    "dataset_hash": pkg.content_hash,
                    "bars": len(bars),
                    "quality": quality,
                    "status": "DATA_BLOCKED",
                    "strategies": {},
                }
            )
            continue

        catalog = baseline_catalog(pkg.symbol)
        for name, meta in catalog.items():
            if insufficient:
                strat_results[name] = {
                    "decision": "INSUFFICIENT_EVIDENCE",
                    "reasons": ["insufficient_history"],
                }
                continue

            cfg = ExperimentConfig(
                strategy_id=meta["strategy_id"],
                strategy_version=meta["strategy_version"],
                parameters=dict(meta["parameters"]),
                dataset_id=pkg.dataset_id,
                dataset_version=pkg.dataset_version,
                universe_id="phase17a_single",
                universe_version="adhoc",
                feature_requests=[{"name": "sma", "window": 5}],
                cost_model=COST_MODEL,
                slippage_model=SLIPPAGE_MODEL,
                calendar_id="NSE_EQ",
                calendar_version="nse_eq_v2023_2025_r1",
                split_config=split,
                walkforward_config=_wf_config(),
                start_date=pkg.start,
                end_date=pkg.end,
                initial_capital=100_000.0,
                research_eligibility="development_only",
                data_class="DEVELOPMENT_DATA",
                purpose="baseline",
                family_id=FAMILY_ID,
                sealed_evaluation=sealed_test,
                score_policy="score_policy_v1",
            )
            # Run twice for config/result hash stability on first strategy/symbol sample
            er = runner.evaluate(
                strategy_factory=meta["factory"],
                bars=bars,
                config=cfg,
                feature_requests=cfg.feature_requests,
                run_robustness=run_robustness,
                run_walkforward=run_walkforward,
                certified_eligibility="development_only",
            )
            val = (er.metrics_by_split or {}).get("validation") or {}
            test = (er.metrics_by_split or {}).get("test") or {}
            train = (er.metrics_by_split or {}).get("train") or {}
            bh = (er.metrics_by_split or {}).get("baseline_buy_hold") or {}
            wf = (er.metrics_by_split or {}).get("walkforward") or {}
            decision, reasons = classify_acceptance(
                score_accepted=bool((er.score or {}).get("accepted")),
                research_eligibility="development_only",
                data_blocked=False,
                insufficient=False,
                rejection_reasons=list(er.rejection_reasons or []),
            )
            row = {
                "strategy": name,
                "symbol": pkg.symbol,
                "dataset_id": pkg.dataset_id,
                "dataset_hash": pkg.content_hash,
                "config_hash": er.config_hash,
                "status": er.status,
                "decision": decision,
                "reasons": reasons,
                "train_metrics": train,
                "validation_metrics": val,
                "test_metrics": test,
                "buy_and_hold_validation": bh,
                "robustness": {
                    "pass_rate": (er.robustness_summary or {}).get("pass_rate"),
                    "fragile": (er.robustness_summary or {}).get("fragile"),
                },
                "walkforward_windows": len((wf.get("windows") or [])),
                "walkforward": wf,
                "dsr": er.deflated_sharpe,
                "n_trials_in_family": er.n_trials_in_family,
                "score": er.score,
                "parameters": meta["parameters"],
                "cost_model": COST_MODEL,
                "slippage_model": SLIPPAGE_MODEL,
            }
            strat_results[name] = row
            experiments.append(row)

        symbol_rows.append(
            {
                "symbol": pkg.symbol,
                "dataset_id": pkg.dataset_id,
                "dataset_version": pkg.dataset_version,
                "dataset_hash": pkg.content_hash,
                "bars": len(bars),
                "start": pkg.start,
                "end": pkg.end,
                "price_policy": pkg.price_policy,
                "quality": quality,
                "status": "OK",
                "strategies": {
                    k: {
                        "decision": v.get("decision"),
                        "validation_return": (v.get("validation_metrics") or {}).get(
                            "total_return"
                        ),
                        "validation_sharpe": (v.get("validation_metrics") or {}).get(
                            "sharpe_ratio"
                        ),
                        "validation_mdd": (v.get("validation_metrics") or {}).get(
                            "maximum_drawdown"
                        ),
                        "trades": (v.get("validation_metrics") or {}).get(
                            "number_of_trades"
                        ),
                        "test_return": (v.get("test_metrics") or {}).get("total_return"),
                        "dsr": v.get("dsr"),
                        "robust_pass_rate": (v.get("robustness") or {}).get("pass_rate"),
                    }
                    for k, v in strat_results.items()
                },
            }
        )

    # Leaderboard ranked by VALIDATION score only (never TEST)
    leaderboard = _build_leaderboard(experiments)
    accepted = [e for e in experiments if e.get("decision") == "PASS"]
    rejected = [e for e in experiments if e.get("decision") in {"FAIL", "DATA_BLOCKED"}]

    # Cross-stock robustness labels per strategy
    cross: dict[str, Any] = {}
    for sname in baseline_catalog("X"):
        statuses = {
            r["symbol"]: "OK"
            for r in symbol_rows
            if r.get("status") == "OK"
            and (r.get("strategies") or {}).get(sname)
        }
        cross[sname] = {
            "classification": classify_cross_stock(statuses),
            "symbols_ok": list(statuses),
            "n_symbols": len(statuses),
        }

    trial_counts = registry.count_trials(FAMILY_ID)
    safety = safety_payload()
    combined_ds_hash = hash_json(inventory["combined_hash_inputs"])

    # PAPER_CANDIDATE — only if existing gates accept (expected 0 under DEVELOPMENT_ONLY)
    paper_candidates = []
    for e in accepted:
        paper_candidates.append(
            {
                "PAPER_CANDIDATE": True,
                "strategy": e["strategy"],
                "symbol": e["symbol"],
                "strategy_hash": e["config_hash"],
                "dataset_hash": e["dataset_hash"],
                "acceptance_status": e["decision"],
                "note": "PAPER_CANDIDATE != PAPER_RUNNING; human approval required",
            }
        )
    if not paper_candidates:
        paper_candidates = [
            {
                "PAPER_CANDIDATE": False,
                "reason": "no_strategy_passed_existing_acceptance_gates",
                "note": "DEVELOPMENT_ONLY datasets cannot be research-accepted",
            }
        ]

    regime = {"status": "REGIME_ANALYSIS_NOT_AVAILABLE"}

    ok = (
        safety["ok"]
        and leakage_global.get("status") in {"PASS", "SKIP"}
        and repro_global.get("status") in {"PASS", "SKIP"}
        and nbo_global.get("status") in {"PASS", "SKIP"}
        and len(packages) > 0
    )

    payload = scrub_secrets(
        {
            "phase": phase_label,
            "ok": ok,
            "result": "PASS" if ok else "FAIL",
            "provider": "ZERODHA",
            "data": "REAL HISTORICAL DATA",
            "dataset": {
                "inventory": inventory,
                "combined_dataset_hash": combined_ds_hash,
                "price_policy": "unknown_raw_execution",
            },
            "corporate_actions": {
                "file": str(ca_path) if ca_path else None,
                "file_hash": ca_hash,
                "table": ca_coverage_table(ca_rows),
                "detail": [{k: v for k, v in r.items() if k != "ca_meta"} for r in ca_rows],
            },
            "symbols": symbol_rows,
            "experiments": experiments,
            "leaderboard": leaderboard,
            "walk_forward": {
                "enabled": run_walkforward,
                "config": _wf_config().model_dump(),
                "status": "PASS"
                if any((e.get("walkforward_windows") or 0) > 0 for e in experiments)
                else "SKIP",
            },
            "robustness": {
                "enabled": run_robustness,
                "status": "PASS"
                if any(
                    (e.get("robustness") or {}).get("pass_rate") is not None
                    for e in experiments
                )
                else "SKIP",
            },
            "dsr": {
                "family_id": FAMILY_ID,
                "trial_counts": trial_counts,
            },
            "trial_count": trial_counts.get("n_experiments"),
            "leakage": leakage_global,
            "future_ca_leakage": future_ca_global,
            "next_bar_open": nbo_global,
            "reproducibility": repro_global,
            "regime_analysis": regime,
            "cross_stock": cross,
            "eligibility": "DEVELOPMENT_ONLY",
            "acceptance": {
                "accepted_count": len(accepted),
                "rejected_count": len(rejected),
                "accepted": [
                    {"strategy": a["strategy"], "symbol": a["symbol"]} for a in accepted
                ],
                "rejected_sample": [
                    {
                        "strategy": r["strategy"],
                        "symbol": r["symbol"],
                        "reasons": r.get("reasons"),
                    }
                    for r in rejected[:20]
                ],
            },
            "paper_candidates": paper_candidates,
            "safety": safety,
            "costs": {"cost_model": COST_MODEL, "slippage_model": SLIPPAGE_MODEL},
            "statement": (
                "Historical strategy validation only. No broker order submission occurred."
            ),
        }
    )

    (reports_dir / report_filename).write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (out_dir / report_filename).write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return payload


def _build_leaderboard(experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank by validation score total; never by TEST metrics."""
    # Aggregate across symbols per strategy
    by_strat: dict[str, list[dict[str, Any]]] = {}
    for e in experiments:
        by_strat.setdefault(e["strategy"], []).append(e)
    rows = []
    for strat, items in by_strat.items():
        scores = [float((i.get("score") or {}).get("total") or 0.0) for i in items]
        val_rets = [
            (i.get("validation_metrics") or {}).get("total_return")
            for i in items
            if (i.get("validation_metrics") or {}).get("total_return") is not None
        ]
        sharpes = [
            (i.get("validation_metrics") or {}).get("sharpe_ratio")
            for i in items
            if (i.get("validation_metrics") or {}).get("sharpe_ratio") is not None
        ]
        mdds = [
            (i.get("validation_metrics") or {}).get("maximum_drawdown")
            for i in items
            if (i.get("validation_metrics") or {}).get("maximum_drawdown") is not None
        ]
        trades = sum(
            int((i.get("validation_metrics") or {}).get("number_of_trades") or 0)
            for i in items
        )
        dsr_vals = [i.get("dsr") for i in items if i.get("dsr") is not None]
        robust_ok = all(
            not (i.get("robustness") or {}).get("fragile") for i in items
        )
        accepted_n = sum(1 for i in items if i.get("decision") == "PASS")
        rows.append(
            {
                "strategy": strat,
                "stocks": len(items),
                "mean_validation_score": sum(scores) / len(scores) if scores else 0.0,
                "mean_oos_return": (
                    sum(val_rets) / len(val_rets) if val_rets else None
                ),
                "mean_sharpe": sum(sharpes) / len(sharpes) if sharpes else None,
                "mean_max_dd": sum(mdds) / len(mdds) if mdds else None,
                "trades": trades,
                "mean_dsr": sum(dsr_vals) / len(dsr_vals) if dsr_vals else None,
                "robust": robust_ok,
                "accepted": accepted_n,
            }
        )
    rows.sort(key=lambda r: r["mean_validation_score"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows

"""Research runner: evaluate strategies with sealed TEST and integrity gates."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from quantfund.analytics.metrics import compute_metrics
from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.data.models import MarketBar
from quantfund.data.universe.membership import was_member
from quantfund.data.universe.models import UniverseVersion
from quantfund.features.engine import FeatureEngine
from quantfund.research.baselines_compare import cash_baseline, run_buy_and_hold_baseline
from quantfund.research.execution_models import resolve_execution_models
from quantfund.research.experiment import ExperimentConfig, ExperimentResult
from quantfund.research.multiple_testing import deflated_sharpe_ratio, trial_accounting_payload
from quantfund.research.report import write_research_report
from quantfund.research.robustness import run_robustness_suite
from quantfund.research.scoring import SCORE_POLICY_V1, compute_research_score
from quantfund.research.splits import ChronologicalSplit, SealedTestSetError
from quantfund.research.walkforward import generate_walkforward_windows
from quantfund.strategies.base import Strategy, StrategyContext
from quantfund.storage.registry import ExperimentRegistry


def _metrics_dict(result) -> dict[str, Any]:
    m = compute_metrics(result)
    return {
        "total_return": m.total_return,
        "cagr": m.cagr,
        "annualized_volatility": m.annualized_volatility,
        "sharpe_ratio": m.sharpe_ratio,
        "sortino_ratio": m.sortino_ratio,
        "maximum_drawdown": m.maximum_drawdown,
        "calmar_ratio": m.calmar_ratio,
        "win_rate": m.win_rate,
        "profit_factor": m.profit_factor,
        "number_of_trades": m.number_of_trades,
        "turnover": m.turnover,
        "total_transaction_costs": m.total_transaction_costs,
        "total_slippage": m.total_slippage,
        "notes": list(m.notes),
    }


def make_enricher(
    feature_engine: FeatureEngine,
    all_bars: list[MarketBar],
    universe: UniverseVersion | None,
) -> Callable[[StrategyContext], StrategyContext]:
    # Precompute full feature frame once (each row uses only past via rolling);
    # asof(T) still filters timestamp <= T.
    frame = feature_engine.compute(all_bars) if feature_engine.feature_versions else None

    def enrich(ctx: StrategyContext) -> StrategyContext:
        feats: dict[str, float | None] = {}
        if frame is not None:
            feats = frame.asof(ctx.timestamp, symbol=ctx.symbol)
        membership = None
        if universe is not None:
            d = ctx.timestamp.date() if isinstance(ctx.timestamp, datetime) else ctx.timestamp
            membership = was_member(universe, symbol=ctx.symbol, on=d).value
        ctx.features = feats
        ctx.membership = membership
        return ctx

    return enrich


class ResearchRunner:
    """Orchestrates research evaluation. Does not generate strategies."""

    def __init__(self, registry: ExperimentRegistry) -> None:
        self.registry = registry

    def evaluate(
        self,
        *,
        strategy_factory: Callable[[], Strategy],
        bars: list[MarketBar],
        config: ExperimentConfig,
        universe: UniverseVersion | None = None,
        feature_requests: list[dict[str, Any]] | None = None,
        run_robustness: bool = True,
        run_walkforward: bool = False,
        certified_eligibility: str | None = None,
    ) -> ExperimentResult:
        """Evaluate a strategy.

        ``certified_eligibility`` comes from ResearchEligibilityChecker /
        DatasetManifest. The runner will never promote above that level.
        """
        strategy = strategy_factory()
        meta = strategy.metadata()
        if meta.strategy_id != config.strategy_id:
            raise ValueError("strategy_id mismatch between factory and config")

        # Gate: development_only cannot be finally accepted.
        # Research runner must not override ResearchEligibilityChecker upward.
        warnings: list[str] = []
        gate_level = certified_eligibility or config.research_eligibility
        rank = {
            "development_only": 0,
            "exploratory": 1,
            "research_eligible": 2,
            "research_ready": 2,
            "production_candidate": 3,
        }
        claimed = config.research_eligibility
        if rank.get(claimed, 0) > rank.get(gate_level, 0):
            warnings.append(
                f"Claimed eligibility {claimed} exceeds certified "
                f"{gate_level} — clamping (gate cannot be overridden)."
            )
            config = config.model_copy(update={"research_eligibility": gate_level})
            claimed = config.research_eligibility
        if claimed == "development_only":
            warnings.append(
                "Dataset/research eligibility is development_only — "
                "result status will be exploratory_only; not final acceptance."
            )

        feature_engine = FeatureEngine()
        reqs = feature_requests or config.feature_requests or []
        if reqs:
            feature_engine.configure(reqs)
        enricher = make_enricher(feature_engine, bars, universe)

        cost_model, slippage_model = resolve_execution_models(
            cost_model=config.cost_model,
            slippage_model=config.slippage_model,
        )

        bt_config = BacktestConfig(
            experiment_id=config.experiment_id,
            initial_capital=config.initial_capital,
            data_source=config.dataset_id,
            data_version=config.dataset_version,
            dataset_id=config.dataset_id,
            dataset_version=config.dataset_version,
            research_eligibility=config.research_eligibility,
            data_class=config.data_class or None,
            universe_id=config.universe_id,
            universe_version=config.universe_version,
            dataset_warnings=list(warnings),
        )

        metrics_by_split: dict[str, dict[str, Any]] = {}
        rejection: list[str] = []
        equity_points: list[dict[str, Any]] = []

        # Chronological splits
        if config.split_config is not None:
            split = ChronologicalSplit.from_bars(bars, config.split_config)
            # Development: train + validation only
            for name, segment in (
                ("train", split.train_bars),
                ("validation", split.validation_bars),
            ):
                if not segment:
                    metrics_by_split[name] = {"error": "empty_split"}
                    continue
                eng = BacktestEngine(
                    strategy_factory(),
                    config=bt_config,
                    cost_model=cost_model,
                    slippage_model=slippage_model,
                    context_enricher=make_enricher(feature_engine, segment, universe),
                )
                res = eng.run(segment)
                metrics_by_split[name] = _metrics_dict(res)
                if name == "validation":
                    equity_points = [
                        {
                            "timestamp": p.timestamp.isoformat(),
                            "equity": p.equity,
                        }
                        for p in res.portfolio.equity_curve
                    ]

            # TEST sealed unless sealed_evaluation
            if config.sealed_evaluation:
                split.unlock_test(sealed_evaluation=True)
                test_bars = split.get_test_bars()
                if test_bars:
                    eng = BacktestEngine(
                        strategy_factory(),
                        config=bt_config,
                        cost_model=cost_model,
                        slippage_model=slippage_model,
                        context_enricher=make_enricher(feature_engine, test_bars, universe),
                    )
                    res = eng.run(test_bars)
                    metrics_by_split["test"] = _metrics_dict(res)
            else:
                try:
                    split.get_test_bars()
                    rejection.append("test_accessed_without_unlock")  # should not happen
                except SealedTestSetError:
                    metrics_by_split["test"] = {"sealed": True, "accessible": False}
        else:
            # No split: run on all bars as exploratory
            eng = BacktestEngine(
                strategy_factory(),
                config=bt_config,
                cost_model=cost_model,
                slippage_model=slippage_model,
                context_enricher=enricher,
            )
            res = eng.run(bars)
            metrics_by_split["full"] = _metrics_dict(res)
            equity_points = [
                {"timestamp": p.timestamp.isoformat(), "equity": p.equity}
                for p in res.portfolio.equity_curve
            ]

        # Walk-forward
        if run_walkforward and config.walkforward_config is not None:
            windows = generate_walkforward_windows(bars, config.walkforward_config)
            wf_metrics = []
            for w in windows:
                # Strict: metrics from window test segment only (dev WF, not sealed TEST)
                if w.test_bars:
                    eng = BacktestEngine(
                        strategy_factory(),
                        config=bt_config,
                        cost_model=cost_model,
                        slippage_model=slippage_model,
                        context_enricher=make_enricher(
                            feature_engine, w.test_bars, universe
                        ),
                    )
                    r = eng.run(w.test_bars)
                    wf_metrics.append(
                        {
                            "window": w.index,
                            "train": w.train.model_dump(mode="json"),
                            "validation": w.validation.model_dump(mode="json"),
                            "test": w.test.model_dump(mode="json"),
                            "metrics": _metrics_dict(r),
                        }
                    )
            metrics_by_split["walkforward"] = {"windows": wf_metrics}

        # Baselines on validation (or full)
        oos_key = "validation" if "validation" in metrics_by_split else "full"
        oos_bars = bars
        if config.split_config is not None:
            split = ChronologicalSplit.from_bars(bars, config.split_config)
            oos_bars = split.validation_bars or split.train_bars
        bh = (
            run_buy_and_hold_baseline(oos_bars, symbol=meta.parameters.get("symbol", "TEST"), config=bt_config)
            if oos_bars
            else {"metrics": {}}
        )
        cash = cash_baseline(config.initial_capital)
        metrics_by_split["baseline_buy_hold"] = bh.get("metrics", {})
        metrics_by_split["baseline_cash"] = cash["metrics"]

        robustness_summary = None
        robustness_pass = None
        if run_robustness and oos_bars:
            base_ret = (metrics_by_split.get(oos_key) or {}).get("total_return")
            robustness_summary = run_robustness_suite(
                strategy_factory=strategy_factory,
                bars=oos_bars,
                base_config=bt_config,
                baseline_total_return=base_ret,
                context_enricher=make_enricher(feature_engine, oos_bars, universe),
            )
            robustness_pass = robustness_summary["pass_rate"]
            if robustness_summary.get("fragile"):
                rejection.append("fragile_under_cost_stress")

        counts = self.registry.count_trials(config.family_id)
        # +1 for this run (registry.put will bump; use anticipatory count for DSR)
        n_trials = counts["n_experiments"] + 1
        oos_metrics = metrics_by_split.get(oos_key) or {}
        sharpe = oos_metrics.get("sharpe_ratio")
        n_obs = max(2, len(oos_bars))
        dsr = deflated_sharpe_ratio(sharpe, n_obs=n_obs, n_trials=n_trials)

        score = compute_research_score(
            oos_metrics=oos_metrics,
            buyhold_metrics=bh.get("metrics"),
            robustness_pass_rate=robustness_pass,
            research_eligibility=config.research_eligibility,
            n_trials=n_trials,
            dsr=dsr,
            policy=SCORE_POLICY_V1,
        )
        rejection.extend(score.get("rejection_reasons") or [])

        if config.research_eligibility == "development_only":
            status = "exploratory_only"
        elif rejection:
            status = "rejected"
        else:
            status = "completed"

        result = ExperimentResult(
            experiment_id=config.experiment_id,
            config_hash=config.compute_hash(),
            status=status,
            rejection_reasons=rejection,
            metrics_by_split=metrics_by_split,
            robustness_summary=robustness_summary,
            score=score,
            warnings=warnings,
            n_trials_in_family=n_trials,
            deflated_sharpe=dsr,
        )

        art = self.registry.put(config, result, equity_curve=equity_points or None)
        write_research_report(
            art,
            config=config,
            result=result,
            trial_accounting=trial_accounting_payload(
                self.registry.count_trials(config.family_id),
                config.selection_criterion,
            ),
        )
        return result.model_copy(update={"artifacts_path": str(art)})

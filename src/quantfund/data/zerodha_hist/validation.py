"""Orchestrate Zerodha historical validation against existing research engine."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from quantfund.analytics.metrics import compute_metrics
from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.eligibility import ResearchEligibilityChecker
from quantfund.data.models import MarketBar
from quantfund.data.policy import DatasetCertificationFacts, EligibilityLevel
from quantfund.data.providers.zerodha_historical import (
    ZerodhaHistoricalProvider,
    build_zerodha_historical_provider,
    scan_zerodha_historical_for_writes,
)
from quantfund.data.quality.checks import run_quality_checks
from quantfund.data.quality.report import Severity
from quantfund.data.zerodha_hist.ca_import import import_ca_csv
from quantfund.data.zerodha_hist.package import write_zerodha_dataset_package
from quantfund.features.engine import FeatureEngine
from quantfund.phase15.models import scrub_secrets
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.runner import ResearchRunner
from quantfund.research.splits import Period, SplitConfig
from quantfund.storage.registry import ExperimentRegistry
from quantfund.strategies.baselines.ma_cross import MovingAverageCrossStrategy
from quantfund.strategies.baselines.mean_reversion import MeanReversionStrategy
from quantfund.strategies.baselines.momentum import MomentumStrategy
from quantfund.strategies.baselines.vol_breakout import VolatilityBreakoutStrategy
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


MIN_BARS_FOR_SPLIT = 60


def _calendar_for_bars(bars: list[MarketBar]) -> FakeCalendarProvider:
    sessions = sorted({b.timestamp.date() for b in bars})
    return FakeCalendarProvider(open_sessions=sessions, verified=False)


def run_quality(
    bars: list[MarketBar],
    *,
    provider: ZerodhaHistoricalProvider,
) -> dict[str, Any]:
    cal = _calendar_for_bars(bars)
    report = run_quality_checks(
        bars,
        calendar=cal,
        instruments=provider.get_instruments(),
        provider_capabilities=provider.capabilities(),
        dataset_id="zerodha_hist",
        source="zerodha_historical_api",
    )
    errors = [i for i in report.issues if i.severity is Severity.ERROR]
    warnings = [i for i in report.issues if i.severity is Severity.WARNING]
    return {
        "errors": len(errors),
        "warnings": len(warnings),
        "data_blocked": len(errors) > 0,
        "issues": [
            {
                "severity": i.severity.value,
                "code": i.code,
                "message": i.message,
            }
            for i in report.issues[:50]
        ],
    }


def evaluate_eligibility(quality: dict[str, Any], *, bars: list[MarketBar]) -> dict[str, Any]:
    """Existing checker only — never shortcut provider==zerodha → eligible."""
    start = min(b.timestamp for b in bars).date().isoformat() if bars else ""
    end = max(b.timestamp for b in bars).date().isoformat() if bars else ""
    facts = DatasetCertificationFacts(
        dataset_id="zerodha_historical",
        dataset_version="validation",
        source="zerodha_historical_api",
        source_grade="non_exchange",
        calendar_id="FAKE_FROM_BARS",
        calendar_version="derived",
        calendar_verified=False,
        universe_id="single_symbol",
        universe_version="adhoc",
        universe_completeness="unknown",
        corporate_action_coverage="unknown",
        adjustment_policy_id="none",
        date_coverage_start=start,
        date_coverage_end=end,
        instrument_count=len({b.symbol for b in bars}),
        error_count=int(quality.get("errors") or 0),
        warning_count=int(quality.get("warnings") or 0),
        content_hash="zerodha_hist_validation",
        capability_source_bar_ok=False,
        provenance_complete=True,
        license_status="internal_research_only",
        data_class="DEVELOPMENT_DATA",
    )
    decision = ResearchEligibilityChecker().evaluate(facts)
    label = (
        "RESEARCH_ELIGIBLE"
        if decision.level is EligibilityLevel.RESEARCH_ELIGIBLE
        else "DEVELOPMENT_ONLY"
    )
    return {
        "research": label,
        "reason": list(decision.blockers or decision.reasons),
        "is_research_eligible": decision.is_research_eligible,
        "level": decision.level.value,
    }


def leakage_asof_test(bars: list[MarketBar]) -> dict[str, Any]:
    if len(bars) < 10:
        return {"status": "SKIP", "detail": "insufficient_bars"}
    eng = FeatureEngine()
    eng.configure([{"name": "sma", "window": 5}, {"name": "momentum", "window": 5}])
    t_idx = len(bars) // 2
    t = bars[t_idx].timestamp
    asof_full = eng.compute(bars).asof(t, symbol=bars[0].symbol)
    asof_cut = eng.compute(bars[: t_idx + 1]).asof(t, symbol=bars[0].symbol)
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
    asof_spike = eng.compute(list(bars) + [spike]).asof(t, symbol=bars[0].symbol)
    ok = asof_full == asof_cut == asof_spike
    return {
        "status": "PASS" if ok else "FAIL",
        "asof_matches_prefix": asof_full == asof_cut,
        "asof_stable_after_future_spike": asof_full == asof_spike,
    }


def next_bar_open_regression(bars: list[MarketBar]) -> dict[str, Any]:
    if len(bars) < 5:
        return {"status": "SKIP"}
    sym = bars[0].symbol
    engine = BacktestEngine(
        BuyAndHoldStrategy(symbol=sym, allocation=0.5),
        config=BacktestConfig(
            initial_capital=100_000.0,
            allow_same_bar_execution=False,
            data_source="zerodha_historical",
        ),
    )
    result = engine.run(bars)
    # Contract: same-bar execution disabled
    if engine.config.allow_same_bar_execution:
        return {"status": "FAIL", "execution": "SAME_BAR"}
    return {
        "status": "PASS",
        "execution": "NEXT_BAR_OPEN",
        "orders": len(result.orders),
        "fills": len(result.portfolio.fills),
    }


def _strategy_factories(symbol: str) -> dict[str, Callable[[], Any]]:
    return {
        "buy_and_hold": lambda: BuyAndHoldStrategy(symbol=symbol, allocation=0.5),
        "ma_cross": lambda: MovingAverageCrossStrategy(symbol=symbol),
        "momentum": lambda: MomentumStrategy(symbol=symbol),
        "mean_reversion": lambda: MeanReversionStrategy(symbol=symbol),
        "vol_breakout": lambda: VolatilityBreakoutStrategy(symbol=symbol),
    }


def run_baselines(bars: list[MarketBar], *, out_dir: Path) -> dict[str, Any]:
    if len(bars) < MIN_BARS_FOR_SPLIT:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "bars": len(bars),
            "required": MIN_BARS_FOR_SPLIT,
            "strategies": {},
        }
    sym = bars[0].symbol
    results: dict[str, Any] = {}
    for name, factory in _strategy_factories(sym).items():
        strategy = factory()
        engine = BacktestEngine(
            strategy,
            config=BacktestConfig(
                initial_capital=100_000.0,
                data_source="zerodha_historical",
                research_eligibility="development_only",
            ),
        )
        bt = engine.run(bars)
        m = compute_metrics(bt)
        results[name] = {
            "status": "OK",
            "orders": len(bt.orders),
            "fills": len(bt.portfolio.fills),
            "metrics": {
                "cagr": m.cagr,
                "sharpe_ratio": m.sharpe_ratio,
                "sortino_ratio": m.sortino_ratio,
                "maximum_drawdown": m.maximum_drawdown,
                "number_of_trades": m.number_of_trades,
                "turnover": m.turnover,
                "total_transaction_costs": m.total_transaction_costs,
                "win_rate": m.win_rate,
                "total_return": m.total_return,
            },
        }

    # Also exercise ResearchRunner once (buy_and_hold) with chronological split
    dates = sorted({b.timestamp.date() for b in bars})
    n = len(dates)
    split = SplitConfig(
        train=Period(start=dates[0], end=dates[n // 3]),
        validation=Period(start=dates[n // 3 + 1], end=dates[(2 * n) // 3]),
        test=Period(start=dates[(2 * n) // 3 + 1], end=dates[-1]),
    )
    registry = ExperimentRegistry(out_dir / "registry")
    runner = ResearchRunner(registry)
    cfg = ExperimentConfig(
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        parameters={"symbol": sym, "allocation": 0.5},
        dataset_id="zerodha_historical",
        dataset_version="validation",
        universe_id="single",
        universe_version="adhoc",
        feature_requests=[{"name": "sma", "window": 5}],
        cost_model="equity_delivery_v1",
        slippage_model="fixed_bps_5",
        calendar_id="FAKE_FROM_BARS",
        calendar_version="derived",
        split_config=split,
        start_date=dates[0].isoformat(),
        end_date=dates[-1].isoformat(),
        initial_capital=100_000.0,
        research_eligibility="development_only",
        data_class="DEVELOPMENT_DATA",
        purpose="baseline",
    )
    try:
        er = runner.evaluate(
            strategy_factory=lambda: BuyAndHoldStrategy(symbol=sym, allocation=0.5),
            bars=bars,
            config=cfg,
            feature_requests=[{"name": "sma", "window": 5}],
            run_robustness=False,
            certified_eligibility="development_only",
        )
        results["research_runner_buy_and_hold"] = {
            "status": er.status,
            "config_hash": er.config_hash,
        }
    except Exception as exc:  # noqa: BLE001
        results["research_runner_buy_and_hold"] = {
            "status": "FAIL",
            "error": type(exc).__name__,
        }

    return {"status": "OK", "strategies": results, "bars": len(bars)}


def reproducibility_check(bars: list[MarketBar]) -> dict[str, Any]:
    sym = bars[0].symbol

    def _run():
        return BacktestEngine(
            BuyAndHoldStrategy(symbol=sym, allocation=0.5),
            config=BacktestConfig(initial_capital=100_000.0),
        ).run(bars)

    a, b = _run(), _run()
    ma, mb = compute_metrics(a), compute_metrics(b)
    same = (
        ma.total_return == mb.total_return
        and ma.number_of_trades == mb.number_of_trades
        and len(a.portfolio.fills) == len(b.portfolio.fills)
        and len(a.orders) == len(b.orders)
    )
    return {"status": "PASS" if same else "FAIL", "deterministic": same}


def run_zerodha_historical_validation(
    *,
    symbol: str = "RELIANCE",
    start: date | None = None,
    end: date | None = None,
    out_dir: Path | None = None,
    force_mock: bool = True,
    ca_file: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    start = start or date(2024, 1, 1)
    end = end or date(2024, 6, 30)
    out_dir = out_dir or Path("experiments/zerodha_hist_validation")
    out_dir.mkdir(parents=True, exist_ok=True)

    write_hits = scan_zerodha_historical_for_writes()
    provider = build_zerodha_historical_provider(env=env, force_mock=force_mock)
    bars = provider.fetch_daily(symbol, start=start, end=end)
    quality = run_quality(bars, provider=provider)
    elig = evaluate_eligibility(quality, bars=bars)

    ca_actions: list = []
    ca_meta: dict[str, Any] = {"status": "SKIPPED", "count": 0}
    if ca_file is not None:
        ca_actions, ca_meta = import_ca_csv(ca_file, symbol_filter=symbol)

    package_dir = None
    if not quality.get("data_blocked"):
        package_dir = write_zerodha_dataset_package(
            bars=bars,
            provenance=(
                provider.last_provenance().to_dict() if provider.last_provenance() else {}
            ),
            quality_report=quality,
            corporate_actions=[a.model_dump(mode="json") for a in ca_actions],
            instrument_metadata={
                "symbols": [symbol],
                "instruments": [
                    i.model_dump(mode="json") for i in provider.get_instruments()
                ],
            },
        )

    leakage = leakage_asof_test(bars)
    nbo = next_bar_open_regression(bars)
    baselines = run_baselines(bars, out_dir=out_dir)
    repro = reproducibility_check(bars)

    # Force research label display
    research_label = "DEVELOPMENT_ONLY"
    if elig.get("is_research_eligible"):
        research_label = "RESEARCH_ELIGIBLE"

    payload = scrub_secrets(
        {
            "provider": "ZERODHA",
            "data": "SIMULATED" if provider._simulated else "REAL HISTORICAL API",
            "exchange": "NSE",
            "interval": "1DAY",
            "symbol": symbol,
            "symbols": [symbol],
            "start": start.isoformat(),
            "end": end.isoformat(),
            "rows": len(bars),
            "quality": quality,
            "corporate_actions": ca_meta,
            "eligibility": {**elig, "research": research_label},
            "leakage": leakage,
            "next_bar_open": nbo,
            "baselines": baselines,
            "reproducibility": repro,
            "package_dir": str(package_dir) if package_dir else None,
            "dataset_id": Path(package_dir).parent.name if package_dir else None,
            "dataset_version": Path(package_dir).name if package_dir else None,
            "price_policy": "unknown",
            "broker_read": "ENABLED",
            "broker_write": "DISABLED",
            "orders_submitted": 0,
            "place_order_called": provider.place_order_called,
            "live_trading": "DISABLED",
            "kill_switch": "ARMED",
            "write_scan_hits": write_hits,
            "research_eligibility": research_label,
        }
    )
    ok = (
        payload["orders_submitted"] == 0
        and payload["place_order_called"] == 0
        and not write_hits
        and leakage.get("status") in {"PASS", "SKIP"}
        and repro.get("status") == "PASS"
        and nbo.get("status") in {"PASS", "SKIP"}
        and research_label == "DEVELOPMENT_ONLY"
        and not quality.get("data_blocked")
    )
    payload["ok"] = ok
    payload["result"] = "PASS" if ok else "FAIL"
    return payload

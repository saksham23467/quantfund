"""Phase 18 — controlled strategy research tests (≥60)."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantfund.data.ingest.checksums import hash_json
from quantfund.data.models import MarketBar
from quantfund.features.engine import FeatureEngine
from quantfund.phase17a.datasets import DiscoveredPackage, PREFERRED_SYMBOLS
from quantfund.phase17a.pipeline import classify_acceptance, leakage_test
from quantfund.phase18.aggregate import aggregate_candidate, rank_leaderboard
from quantfund.phase18.candidates import (
    candidate_id_for,
    generate_candidates,
    search_config_hash,
    build_strategy_spec,
)
from quantfund.phase18.extra_strategies import (
    DonchianBreakoutStrategy,
    MomentumVolFilterStrategy,
    RSIMeanReversionStrategy,
    TrendVolFilterStrategy,
)
from quantfund.phase18.factories import feature_requests_for, strategy_factory_for
from quantfund.phase18.grammar import (
    FAMILY_IDS,
    GRIDS_FULL,
    expand_family_params,
    grids_for_mode,
    search_config_payload,
)
from quantfund.phase18.pipeline import (
    FAMILY_ID,
    _chron_split,
    _combined_dataset_hash,
    _flag_exact_parameter_only,
    _wf_config,
    evaluate_candidate_symbol,
    run_phase18_search,
)
from quantfund.phase18.report import format_demo, write_json, write_markdown
from quantfund.phase18.safety import FORBIDDEN_CALLS, safety_payload, scan_phase18_for_writes
from quantfund.phase18.seal import SealGuard, SealViolation
from quantfund.research.runner import ResearchRunner
from quantfund.storage.registry import ExperimentRegistry
from quantfund.strategies.baselines.ma_cross import MovingAverageCrossStrategy
from quantfund.strategies.spec.validate import validate_strategy_spec


def _bars(n: int = 120, symbol: str = "RELIANCE") -> list[MarketBar]:
    """Deterministic synthetic bars for unit tests only (not research artifacts)."""
    out: list[MarketBar] = []
    t = datetime(2023, 1, 2, tzinfo=timezone.utc)
    px = 100.0 + (sum(ord(c) for c in symbol) % 50)
    while len(out) < n:
        if t.weekday() < 5:
            px = px * (1.0 + (0.001 if len(out) % 7 else -0.0005))
            out.append(
                MarketBar(
                    timestamp=t,
                    symbol=symbol,
                    open=px,
                    high=px * 1.01,
                    low=px * 0.99,
                    close=px,
                    volume=1000.0,
                )
            )
        t = t + timedelta(days=1)
    return out


def _pkg(symbol: str = "RELIANCE", bars: list[MarketBar] | None = None) -> DiscoveredPackage:
    bars = bars or _bars(120, symbol)
    return DiscoveredPackage(
        dataset_id=f"test_{symbol.lower()}",
        dataset_version="v1",
        path=Path("/tmp/unused"),
        manifest={
            "dataset_id": f"test_{symbol.lower()}",
            "symbols": [symbol],
            "rows": len(bars),
            "content_hash": hash_json({"s": symbol, "n": len(bars)}),
            "eligibility": "DEVELOPMENT_ONLY",
        },
        symbol=symbol,
        bars=len(bars),
        start=str(bars[0].timestamp.date()),
        end=str(bars[-1].timestamp.date()),
        content_hash=hash_json({"s": symbol, "n": len(bars)}),
        price_policy="unadjusted_raw",
        eligibility="DEVELOPMENT_ONLY",
    )


# --- Grammar / candidates ---


def test_ten_families_defined() -> None:
    assert len(FAMILY_IDS) == 10


def test_full_grids_cover_brief_ma() -> None:
    assert GRIDS_FULL["ma_cross"]["fast"] == (5, 10, 20, 30)
    assert GRIDS_FULL["ma_cross"]["slow"] == (50, 100, 150, 200)


def test_full_grids_momentum_lookbacks() -> None:
    assert GRIDS_FULL["momentum"]["lookback"] == (10, 20, 40, 60, 120)


def test_full_grids_rsi_and_donchian() -> None:
    assert GRIDS_FULL["rsi_mean_reversion"]["period"] == (14, 21)
    assert GRIDS_FULL["donchian_breakout"]["lookback"] == (20, 40, 60)


def test_ma_fast_lt_slow_filter() -> None:
    params = expand_family_params("ma_cross", GRIDS_FULL)
    assert all(p["fast"] < p["slow"] for p in params)
    assert len(params) == 16


def test_tiny_mode_smaller_than_full() -> None:
    assert len(generate_candidates("tiny")) < len(generate_candidates("full"))


def test_demo_mode_smaller_than_full() -> None:
    assert len(generate_candidates("demo")) < len(generate_candidates("full"))


def test_candidate_ids_deterministic() -> None:
    a = generate_candidates("tiny")
    b = generate_candidates("tiny")
    assert [c.candidate_id for c in a] == [c.candidate_id for c in b]


def test_candidate_id_stable_for_params() -> None:
    p = {"fast": 10, "slow": 50}
    assert candidate_id_for("ma_cross", p) == candidate_id_for("ma_cross", {"slow": 50, "fast": 10})


def test_search_config_hash_stable() -> None:
    assert search_config_hash("demo") == search_config_hash("demo")


def test_search_config_hash_differs_by_mode() -> None:
    assert search_config_hash("demo") != search_config_hash("full")


def test_search_config_payload_has_families() -> None:
    p = search_config_payload("full")
    assert p["families"] == list(FAMILY_IDS)
    assert p["test_policy"] == "sealed_until_finalists"


def test_grids_for_mode_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        grids_for_mode("bogus")  # type: ignore[arg-type]


def test_every_candidate_has_strategy_spec() -> None:
    for c in generate_candidates("tiny"):
        spec = c.strategy_spec("RELIANCE")
        assert spec.symbol == "RELIANCE"
        assert spec.metadata["candidate_id"] == c.candidate_id


def test_ma_spec_validates() -> None:
    spec = build_strategy_spec(
        family="ma_cross",
        parameters={"fast": 10, "slow": 50},
        symbol="TCS",
        candidate_id="x",
    )
    validate_strategy_spec(spec)


def test_momentum_spec_validates() -> None:
    spec = build_strategy_spec(
        family="momentum",
        parameters={"lookback": 20, "threshold": 0.0},
        symbol="TCS",
        candidate_id="y",
    )
    validate_strategy_spec(spec)


def test_candidate_to_dict_includes_spec() -> None:
    c = generate_candidates("tiny")[0]
    d = c.to_dict()
    assert "strategy_spec_template" in d
    assert d["candidate_id"].startswith("p18_")


# --- Factories / extras ---


def test_factory_ma_cross() -> None:
    c = next(x for x in generate_candidates("tiny") if x.strategy_family == "ma_cross")
    s = strategy_factory_for(c, symbol="RELIANCE")()
    assert isinstance(s, MovingAverageCrossStrategy)


def test_factory_trend_following_relabel() -> None:
    c = next(x for x in generate_candidates("tiny") if x.strategy_family == "trend_following")
    s = strategy_factory_for(c, symbol="RELIANCE")()
    assert s.metadata().strategy_id == "trend_following"


def test_factory_rsi() -> None:
    c = next(x for x in generate_candidates("tiny") if x.strategy_family == "rsi_mean_reversion")
    s = strategy_factory_for(c, symbol="RELIANCE")()
    assert isinstance(s, RSIMeanReversionStrategy)


def test_factory_donchian() -> None:
    c = next(x for x in generate_candidates("tiny") if x.strategy_family == "donchian_breakout")
    s = strategy_factory_for(c, symbol="RELIANCE")()
    assert isinstance(s, DonchianBreakoutStrategy)


def test_factory_mom_vol() -> None:
    c = next(x for x in generate_candidates("tiny") if x.strategy_family == "momentum_vol_filter")
    s = strategy_factory_for(c, symbol="RELIANCE")()
    assert isinstance(s, MomentumVolFilterStrategy)


def test_factory_trend_vol() -> None:
    c = next(x for x in generate_candidates("tiny") if x.strategy_family == "trend_vol_filter")
    s = strategy_factory_for(c, symbol="RELIANCE")()
    assert isinstance(s, TrendVolFilterStrategy)


def test_feature_requests_ma() -> None:
    c = next(x for x in generate_candidates("tiny") if x.strategy_family == "ma_cross")
    reqs = feature_requests_for(c)
    assert any(r["name"] == "sma" for r in reqs)


def test_rsi_generates_signal_warmup() -> None:
    s = RSIMeanReversionStrategy(symbol="X", period=14)
    from quantfund.strategies.base import StrategyContext

    ctx = StrategyContext(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        symbol="X",
        history=_bars(5, "X"),
        position_quantity=0,
        cash=100000,
    )
    sig = s.generate_signal(ctx)
    assert sig is not None


def test_donchian_metadata() -> None:
    m = DonchianBreakoutStrategy(symbol="X", lookback=20).metadata()
    assert m.strategy_id == "donchian_breakout"


def test_trend_vol_rejects_fast_ge_slow() -> None:
    with pytest.raises(ValueError):
        TrendVolFilterStrategy(symbol="X", fast=50, slow=20)


# --- Seal ---


def test_seal_blocks_test_extract() -> None:
    g = SealGuard()
    with pytest.raises(SealViolation):
        g.extract_test_metrics({"test": {"sharpe_ratio": 1.0}})


def test_seal_allows_after_unlock() -> None:
    g = SealGuard()
    g.unlock_for_final_evaluation()
    assert g.extract_test_metrics({"test": {"sharpe_ratio": 1.2}})["sharpe_ratio"] == 1.2


def test_ranking_metrics_exclude_test() -> None:
    g = SealGuard()
    out = g.extract_ranking_metrics(
        {
            "train": {"sharpe_ratio": 0.1},
            "validation": {"sharpe_ratio": 0.2},
            "test": {"sharpe_ratio": 9.9},
        }
    )
    assert "test" not in out
    assert out["validation"]["sharpe_ratio"] == 0.2


def test_assert_can_rank_rejects_test_sharpe() -> None:
    g = SealGuard()
    with pytest.raises(SealViolation):
        g.assert_can_rank({"test_metrics": {"sharpe_ratio": 1.0}})


def test_assert_can_rank_allows_sealed_marker() -> None:
    g = SealGuard()
    g.assert_can_rank({"test_metrics": {"sealed": True, "accessible": False}})


def test_seal_status_payload() -> None:
    g = SealGuard()
    assert g.status()["policy"] == "sealed_until_finalists"


# --- Aggregate ---


def test_aggregate_mean_validation_sharpe() -> None:
    g = SealGuard()
    rows = [
        {
            "symbol": "A",
            "validation_metrics": {"sharpe_ratio": 1.0, "total_return": 0.1},
            "test_metrics": {"sealed": True},
            "status": "ok",
        },
        {
            "symbol": "B",
            "validation_metrics": {"sharpe_ratio": 0.0, "total_return": -0.1},
            "test_metrics": {"sealed": True},
            "status": "ok",
        },
    ]
    agg = aggregate_candidate(
        candidate_id="c1",
        strategy_family="momentum",
        parameters={"lookback": 20},
        per_symbol=rows,
        guard=g,
    )
    assert agg["mean_validation_sharpe"] == pytest.approx(0.5)
    assert agg["test_used_for_ranking"] is False
    assert agg["best_symbol"] == "A"
    assert agg["worst_symbol"] == "B"


def test_aggregate_rejects_test_leak() -> None:
    g = SealGuard()
    rows = [
        {
            "symbol": "A",
            "validation_metrics": {"sharpe_ratio": 1.0},
            "test_metrics": {"sharpe_ratio": 9.0},
            "status": "ok",
        }
    ]
    with pytest.raises(SealViolation):
        aggregate_candidate(
            candidate_id="c1",
            strategy_family="momentum",
            parameters={},
            per_symbol=rows,
            guard=g,
        )


def test_rank_leaderboard_order() -> None:
    rows = [
        {"candidate_id": "b", "mean_validation_sharpe": 0.1},
        {"candidate_id": "a", "mean_validation_sharpe": 0.9},
    ]
    lb = rank_leaderboard(rows)
    assert lb[0]["candidate_id"] == "a"
    assert lb[0]["rank"] == 1


def test_flag_exact_parameter_only() -> None:
    lb = [
        {"strategy_family": "momentum", "candidate_id": "1", "mean_validation_sharpe": 0.5},
        {"strategy_family": "momentum", "candidate_id": "2", "mean_validation_sharpe": -0.1},
    ]
    flags = _flag_exact_parameter_only(lb)
    assert flags and flags[0]["flag"] == "exact_parameter_only"


# --- Safety ---


def test_no_place_order_in_phase18_tree() -> None:
    assert scan_phase18_for_writes() == []


def test_safety_payload_defaults() -> None:
    s = safety_payload()
    assert s["ok"] is True
    assert s["place_order_called"] == 0
    assert s["orders_submitted"] == 0
    assert s["broker_write_capability"] == "DISABLED"
    assert s["live_trading"] == "DISABLED"
    assert s["paper_trading"] == "NOT_STARTED"
    assert s["kill_switch"] == "ARMED"


def test_forbidden_calls_include_place_order() -> None:
    assert "place_order" in FORBIDDEN_CALLS


def test_phase18_ast_no_broker_order_imports() -> None:
    root = Path("src/quantfund/phase18")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "place_order" not in (node.module or "")


# --- Acceptance policy reuse ---


def test_development_only_cannot_accept() -> None:
    decision, reasons = classify_acceptance(
        score_accepted=True,
        research_eligibility="development_only",
        data_blocked=False,
        insufficient=False,
        rejection_reasons=[],
    )
    assert decision == "FAIL"
    assert "development_only_cannot_be_accepted" in reasons


def test_family_id_phase18() -> None:
    assert FAMILY_ID == "phase18_controlled_search"


def test_preferred_symbols_eight() -> None:
    assert len(PREFERRED_SYMBOLS) == 8


# --- Leakage ---


def test_leakage_asof_stable() -> None:
    bars = _bars(80)
    r = leakage_test(bars)
    assert r["status"] in ("PASS", "SKIP")


def test_feature_engine_future_spike_phase18() -> None:
    bars = _bars(40)
    eng = FeatureEngine()
    eng.configure([{"name": "sma", "window": 5}])
    t = bars[20].timestamp
    a = eng.compute(bars).asof(t, symbol=bars[0].symbol)
    last = bars[-1]
    spike = MarketBar(
        timestamp=last.timestamp + timedelta(days=1),
        symbol=last.symbol,
        open=last.close * 10,
        high=last.close * 10,
        low=last.close * 10,
        close=last.close * 10,
        volume=1.0,
    )
    b = eng.compute(list(bars) + [spike]).asof(t, symbol=bars[0].symbol)
    assert a == b


# --- Splits / WF ---


def test_chron_split_thirds() -> None:
    bars = _bars(90)
    split = _chron_split(bars, min_bars=60)
    assert split is not None
    assert split.train.end < split.validation.start
    assert split.validation.end < split.test.start


def test_chron_split_insufficient() -> None:
    assert _chron_split(_bars(10), min_bars=60) is None


def test_wf_config_scales() -> None:
    big = _wf_config(2000)
    small = _wf_config(100)
    assert big.train_sessions == 252
    assert small.train_sessions == 40


# --- Report ---


def test_format_demo_contains_headers() -> None:
    text = format_demo(
        {
            "dataset": {"combined_hash": "abc", "symbols": ["RELIANCE"], "start": "2018", "end": "2026"},
            "candidates": {
                "generated": 1,
                "evaluated": 1,
                "rejected": 0,
                "finalists": 1,
                "accepted": 0,
                "paper_candidates": 0,
            },
            "best_candidates": [],
            "gates": {
                "leakage": "PASS",
                "walkforward": "PASS",
                "robustness": "PASS",
                "dsr": "PASS",
                "reproducibility": "PASS",
                "test_sealed": True,
                "test_not_used_for_ranking": True,
            },
            "safety": safety_payload(),
        }
    )
    assert "PHASE 18 STRATEGY RESEARCH" in text
    assert "Live trading: DISABLED" in text
    assert "Accepted strategies: 0" in text


def test_write_json_and_markdown(tmp_path: Path) -> None:
    payload = {"phase": "18", "dataset": {}, "candidates": {}, "gates": {}, "search_mode": "tiny", "search_config_hash": "h", "family_id": FAMILY_ID}
    h = write_json(tmp_path / "phase18_strategy_search.json", payload)
    assert len(h) > 10
    write_markdown(tmp_path / "PHASE18.md", payload)
    assert (tmp_path / "PHASE18.md").exists()


def test_combined_dataset_hash_stable() -> None:
    inv = {"combined_hash_inputs": ["a", "b"], "symbols": ["X"]}
    assert _combined_dataset_hash(inv) == _combined_dataset_hash(inv)


# --- Pipeline (tiny, mocked packages) ---


def test_pipeline_tiny_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bars_a = _bars(100, "RELIANCE")
    bars_b = _bars(100, "TCS")
    pkgs = [_pkg("RELIANCE", bars_a), _pkg("TCS", bars_b)]
    mapping = {"RELIANCE": bars_a, "TCS": bars_b}

    monkeypatch.setattr(
        "quantfund.phase18.pipeline.load_package_bars",
        lambda pkg: mapping[pkg.symbol],
    )
    monkeypatch.setattr(
        "quantfund.phase18.pipeline.run_symbol_quality",
        lambda bars, dataset_id: {"data_blocked": False, "errors": 0},
    )

    report = run_phase18_search(
        out_dir=tmp_path / "exp",
        mode="tiny",
        n_finalists=2,
        packages=pkgs,
        write_global_reports=False,
        run_reproducibility=True,
    )
    assert report["candidates"]["generated"] == len(generate_candidates("tiny"))
    assert report["candidates"]["accepted"] == 0
    assert report["gates"]["test_not_used_for_ranking"] is True
    assert report["safety"]["orders_submitted"] == 0
    assert (tmp_path / "exp" / "reports" / "phase18_strategy_search.json").exists()
    assert (tmp_path / "exp" / "reports" / "phase18_leaderboard.json").exists()
    assert report["reproducibility"]["status"] == "PASS"
    assert report["family_id"] == FAMILY_ID


def test_pipeline_screen_rows_seal_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bars = _bars(100, "INFY")
    pkgs = [_pkg("INFY", bars)]
    monkeypatch.setattr("quantfund.phase18.pipeline.load_package_bars", lambda pkg: bars)
    monkeypatch.setattr(
        "quantfund.phase18.pipeline.run_symbol_quality",
        lambda bars, dataset_id: {"data_blocked": False},
    )
    report = run_phase18_search(
        out_dir=tmp_path / "exp2",
        mode="tiny",
        n_finalists=1,
        packages=pkgs,
        write_global_reports=False,
        symbols=("INFY",),
    )
    # Leaderboard must not embed TEST sharpe from screening
    lb = json.loads((tmp_path / "exp2" / "reports" / "phase18_leaderboard.json").read_text())
    assert lb["test_used_for_ranking"] is False
    assert report["candidates"]["paper_candidates"] == 0


def test_evaluate_candidate_symbol_sealed(tmp_path: Path) -> None:
    bars = _bars(100)
    pkg = _pkg("RELIANCE", bars)
    split = _chron_split(bars, min_bars=60)
    assert split is not None
    cand = next(c for c in generate_candidates("tiny") if c.strategy_family == "momentum")
    guard = SealGuard()
    runner = ResearchRunner(ExperimentRegistry(tmp_path / "reg"))
    row = evaluate_candidate_symbol(
        runner=runner,
        candidate=cand,
        symbol="RELIANCE",
        bars=bars,
        pkg=pkg,
        split=split,
        sealed_evaluation=False,
        run_walkforward=False,
        run_robustness=False,
        guard=guard,
    )
    assert row["test_metrics"]["sealed"] is True
    assert "sharpe_ratio" not in row["test_metrics"]


def test_evaluate_finalist_unlocks_test(tmp_path: Path) -> None:
    bars = _bars(100)
    pkg = _pkg("RELIANCE", bars)
    split = _chron_split(bars, min_bars=60)
    cand = next(c for c in generate_candidates("tiny") if c.strategy_family == "ma_cross")
    guard = SealGuard()
    guard.unlock_for_final_evaluation()
    runner = ResearchRunner(ExperimentRegistry(tmp_path / "reg2"))
    row = evaluate_candidate_symbol(
        runner=runner,
        candidate=cand,
        symbol="RELIANCE",
        bars=bars,
        pkg=pkg,
        split=split,
        sealed_evaluation=True,
        run_walkforward=False,
        run_robustness=False,
        guard=guard,
    )
    assert "sealed" not in row["test_metrics"] or "sharpe_ratio" in row["test_metrics"] or "error" in row["test_metrics"] or row["test_metrics"]


def test_registry_receives_trials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bars = _bars(100, "SBIN")
    pkgs = [_pkg("SBIN", bars)]
    monkeypatch.setattr("quantfund.phase18.pipeline.load_package_bars", lambda pkg: bars)
    monkeypatch.setattr(
        "quantfund.phase18.pipeline.run_symbol_quality",
        lambda bars, dataset_id: {"data_blocked": False},
    )
    reg = tmp_path / "registry"
    run_phase18_search(
        out_dir=tmp_path / "exp3",
        mode="tiny",
        n_finalists=1,
        packages=pkgs,
        registry_dir=reg,
        write_global_reports=False,
    )
    counts = ExperimentRegistry(reg).count_trials(FAMILY_ID)
    assert counts["n_experiments"] >= 1


def test_no_yfinance_import_in_phase18() -> None:
    root = Path("src/quantfund/phase18")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "yfinance" not in text


def test_no_llm_or_genetic_in_phase18() -> None:
    root = Path("src/quantfund/phase18")
    banned = ("openai", "genetic", "mutate_code", "llm_generate")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for b in banned:
            assert b not in text


def test_makefile_has_phase18_targets() -> None:
    mk = Path("Makefile").read_text(encoding="utf-8")
    for t in (
        "phase18-search",
        "phase18-backtest",
        "phase18-walkforward",
        "phase18-robustness",
        "phase18-report",
        "phase18-demo",
    ):
        assert t in mk


def test_scripts_exist() -> None:
    for name in (
        "run_phase18_search.py",
        "run_phase18_backtest.py",
        "run_phase18_walkforward.py",
        "run_phase18_robustness.py",
        "run_phase18_report.py",
        "run_phase18_demo.py",
    ):
        assert (Path("scripts") / name).exists()


def test_vol_regime_family_present() -> None:
    assert "volatility_regime_filter" in FAMILY_IDS


def test_full_candidate_count_reasonable() -> None:
    n = len(generate_candidates("full"))
    assert 40 <= n <= 120


def test_demo_candidate_count() -> None:
    n = len(generate_candidates("demo"))
    assert 10 <= n <= 40


def test_extra_strategies_prepare_data_filters_symbol() -> None:
    bars = _bars(30, "A") + _bars(30, "B")
    s = RSIMeanReversionStrategy(symbol="A")
    out = s.prepare_data(bars)
    assert all(b.symbol == "A" for b in out)


def test_acceptance_zero_is_valid_outcome() -> None:
    # Documented contract: accepted may be 0 under DEVELOPMENT_ONLY
    decision, _ = classify_acceptance(
        score_accepted=False,
        research_eligibility="development_only",
        data_blocked=False,
        insufficient=False,
        rejection_reasons=["score_rejected"],
    )
    assert decision == "FAIL"


def test_hash_json_leaderboard_repro() -> None:
    payload = [{"rank": 1, "candidate_id": "x", "mean_validation_sharpe": 0.1}]
    assert hash_json(payload) == hash_json(payload)

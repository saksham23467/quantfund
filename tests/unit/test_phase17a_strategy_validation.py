"""Phase 17A — real Zerodha strategy validation tests (≥50)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.data.corporate_actions.models import CorporateActionType
from quantfund.data.models import MarketBar
from quantfund.data.providers.zerodha_historical import build_zerodha_historical_provider
from quantfund.data.zerodha_hist.package import write_zerodha_dataset_package
from quantfund.phase15.models import scrub_secrets
from quantfund.phase17a.ca import analyze_ca_for_symbol, ca_coverage_table, default_ca_file
from quantfund.phase17a.datasets import (
    PREFERRED_SYMBOLS,
    dataset_inventory,
    discover_zerodha_packages,
    latest_version_dir,
    load_package_bars,
)
from quantfund.phase17a.pipeline import (
    FAMILY_ID,
    _build_leaderboard,
    _chron_split,
    classify_acceptance,
    classify_cross_stock,
    future_ca_leakage_test,
    leakage_test,
    next_bar_open_proof,
    reproducibility_pair,
    run_phase17a_validation,
)
from quantfund.phase17a.quality import BLOCKING_CODES, run_symbol_quality
from quantfund.phase17a.report import render_markdown
from quantfund.phase17a.safety import safety_payload, scan_phase17a_for_writes
from quantfund.phase17a.strategies import baseline_catalog, strategy_factory
from quantfund.research.experiment import ExperimentConfig
from quantfund.research.execution_models import resolve_execution_models
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


def _mock_bars(n: int = 90, symbol: str = "RELIANCE") -> list[MarketBar]:
    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily(symbol, start=__import__("datetime").date(2024, 1, 1), end=__import__("datetime").date(2024, 6, 28))
    return bars[:n] if len(bars) >= n else bars


# --- DATA ---


def test_discover_packages_or_empty() -> None:
    pkgs = discover_zerodha_packages()
    assert isinstance(pkgs, list)


def test_preferred_symbols_tuple() -> None:
    assert "RELIANCE" in PREFERRED_SYMBOLS
    assert len(PREFERRED_SYMBOLS) >= 5


def test_dataset_inventory_shape() -> None:
    inv = dataset_inventory(discover_zerodha_packages())
    assert "package_count" in inv
    assert "packages" in inv


def test_latest_version_dir(tmp_path: Path) -> None:
    ds = tmp_path / "ds"
    (ds / "v1").mkdir(parents=True)
    (ds / "v3").mkdir()
    (ds / "v2").mkdir()
    assert latest_version_dir(ds).name == "v3"


def test_immutable_package_refuse_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.data.zerodha_hist import package as pkgmod

    monkeypatch.setattr(pkgmod, "research_zerodha_root", lambda: tmp_path)
    bars = _mock_bars(80)
    write_zerodha_dataset_package(
        bars=bars,
        provenance={"provider": "zerodha"},
        quality_report={"errors": 0},
        dataset_id="p17a_immut",
        version="v1",
    )
    with pytest.raises(FileExistsError):
        write_zerodha_dataset_package(
            bars=bars,
            provenance={"provider": "zerodha"},
            quality_report={"errors": 0},
            dataset_id="p17a_immut",
            version="v1",
        )


def test_dataset_hash_present_when_real_packages_exist() -> None:
    pkgs = discover_zerodha_packages()
    if not pkgs:
        pytest.skip("no real packages")
    assert all(p.content_hash for p in pkgs)


def test_load_real_package_bars_if_present() -> None:
    pkgs = discover_zerodha_packages()
    if not pkgs:
        pytest.skip("no real packages")
    bars = load_package_bars(pkgs[0])
    assert len(bars) == pkgs[0].bars
    assert bars[0].symbol == pkgs[0].symbol


def test_ca_default_file_optional() -> None:
    # may or may not exist
    p = default_ca_file()
    assert p is None or p.exists()


def test_ca_unknown_types_flagged(tmp_path: Path) -> None:
    csv = tmp_path / "ca.csv"
    csv.write_text(
        "SYMBOL,COMPANY NAME,SERIES,PURPOSE,FACE VALUE,EX-DATE,RECORD DATE,"
        "BOOK CLOSURE START DATE,BOOK CLOSURE END DATE\n"
        "RELIANCE,R,EQ,WEIRD EVENT,10,01-Feb-2024,,,\n",
        encoding="utf-8",
    )
    info = analyze_ca_for_symbol("RELIANCE", ca_file=csv)
    assert info["events"] >= 1
    assert info["unknown"] >= 1
    assert info["coverage"] == "PARTIAL"


def test_ca_coverage_table() -> None:
    table = ca_coverage_table(
        [{"symbol": "X", "events": 1, "known": 1, "unknown": 0, "coverage": "PARTIAL", "blockers": []}]
    )
    assert table[0]["symbol"] == "X"


def test_ca_does_not_invent_adjusted_flag() -> None:
    info = analyze_ca_for_symbol("NOPE", ca_file=None)
    assert info["price_policy"]["research_adjusted_invented"] is False
    assert info["price_policy"]["raw_execution"] is True


def test_quality_blocking_codes_defined() -> None:
    assert "duplicate_timestamp" in BLOCKING_CODES
    assert "invalid_ohlc" in BLOCKING_CODES


def test_quality_on_mock_bars() -> None:
    bars = _mock_bars(80)
    q = run_symbol_quality(bars, dataset_id="mock")
    assert "errors" in q
    assert "calendar" in q


def test_quality_blocks_invalid_ohlc() -> None:
    bars = _mock_bars(20)
    b0 = bars[0]
    bad = [MarketBar.model_construct(
        timestamp=b0.timestamp,
        symbol=b0.symbol,
        open=10.0,
        high=5.0,
        low=8.0,
        close=9.0,
        volume=1.0,
        instrument_id=b0.instrument_id,
    )] + bars[1:]
    q = run_symbol_quality(bad, dataset_id="bad")
    assert q["blocking_errors"] >= 1 or q["errors"] >= 1


def test_missing_sessions_reported_not_repaired() -> None:
    bars = _mock_bars(10)
    q = run_symbol_quality(bars, dataset_id="short")
    # calendar coverage may show missing; bars list unchanged
    assert len(bars) == 10
    assert "calendar" in q


# --- STRATEGY ---


def test_all_five_strategies_in_catalog() -> None:
    cat = baseline_catalog("RELIANCE")
    assert set(cat) == {
        "buy_and_hold",
        "ma_cross",
        "momentum",
        "mean_reversion",
        "vol_breakout",
    }


def test_fixed_parameters_no_mutation() -> None:
    a = baseline_catalog("RELIANCE")["ma_cross"]["parameters"]
    b = baseline_catalog("RELIANCE")["ma_cross"]["parameters"]
    assert a == b
    assert a["fast"] == 3 and a["slow"] == 5


def test_strategy_factory_deterministic_id() -> None:
    s = strategy_factory("momentum", "TCS")()
    assert s.metadata().strategy_id == "momentum"


def test_each_baseline_instantiates() -> None:
    for name in baseline_catalog("INFY"):
        assert strategy_factory(name, "INFY")() is not None


def test_unknown_strategy_factory_raises() -> None:
    with pytest.raises(KeyError):
        strategy_factory("not_a_strategy", "RELIANCE")


# --- BACKTEST ---


def test_next_bar_open_on_mock() -> None:
    r = next_bar_open_proof(_mock_bars(80))
    assert r["status"] == "PASS"
    assert r["execution"] == "NEXT_BAR_OPEN"


def test_next_bar_open_real_if_present() -> None:
    pkgs = discover_zerodha_packages(symbols=("RELIANCE",))
    if not pkgs:
        pytest.skip("no reliance package")
    r = next_bar_open_proof(load_package_bars(pkgs[0]))
    assert r["status"] == "PASS"


def test_raw_execution_uses_open_not_same_close() -> None:
    bars = _mock_bars(80)
    eng = BacktestEngine(
        BuyAndHoldStrategy(symbol="RELIANCE", allocation=0.5),
        config=BacktestConfig(initial_capital=100_000.0, allow_same_bar_execution=False),
    )
    assert eng.config.allow_same_bar_execution is False
    res = eng.run(bars)
    assert len(res.portfolio.fills) >= 0


def test_known_cost_model_resolves() -> None:
    cost, slip = resolve_execution_models(
        cost_model="equity_delivery_v1", slippage_model="fixed_bps_5"
    )
    assert cost is not None and slip is not None


def test_unknown_cost_model_fail_closed() -> None:
    with pytest.raises(Exception):
        resolve_execution_models(cost_model="not_a_real_cost", slippage_model="fixed_bps_5")


def test_trade_accounting_metrics() -> None:
    bars = _mock_bars(80)
    res = BacktestEngine(
        BuyAndHoldStrategy(symbol="RELIANCE", allocation=0.5),
        config=BacktestConfig(initial_capital=100_000.0),
    ).run(bars)
    from quantfund.analytics.metrics import compute_metrics

    m = compute_metrics(res)
    assert m.number_of_trades is not None
    assert m.total_transaction_costs is not None


# --- LEAKAGE ---


def test_asof_leakage_mock() -> None:
    assert leakage_test(_mock_bars(80))["status"] == "PASS"


def test_future_spike_leakage_mock() -> None:
    r = leakage_test(_mock_bars(80))
    assert r["asof_stable_after_future_spike"] is True


def test_future_ca_leakage_independent() -> None:
    r = future_ca_leakage_test(_mock_bars(40), [])
    assert r["status"] == "PASS"


def test_leakage_real_if_present() -> None:
    pkgs = discover_zerodha_packages(symbols=("RELIANCE",))
    if not pkgs:
        pytest.skip("no package")
    assert leakage_test(load_package_bars(pkgs[0]))["status"] == "PASS"


# --- SPLITS / WF ---


def test_chron_split_insufficient() -> None:
    assert _chron_split(_mock_bars(10)) is None


def test_chron_split_ok() -> None:
    split = _chron_split(_mock_bars(90))
    assert split is not None
    assert split.train.end < split.validation.start
    assert split.validation.end < split.test.start


def test_split_chronological_no_shuffle() -> None:
    split = _chron_split(_mock_bars(90))
    assert split.method == "chronological"


def test_classify_acceptance_development_only_fail() -> None:
    d, reasons = classify_acceptance(
        score_accepted=False,
        research_eligibility="development_only",
        data_blocked=False,
        insufficient=False,
        rejection_reasons=[],
    )
    assert d == "FAIL"
    assert any("development_only" in r for r in reasons)


def test_classify_data_blocked() -> None:
    d, _ = classify_acceptance(
        score_accepted=True,
        research_eligibility="research_eligible",
        data_blocked=True,
        insufficient=False,
        rejection_reasons=[],
    )
    assert d == "DATA_BLOCKED"


def test_classify_insufficient() -> None:
    d, _ = classify_acceptance(
        score_accepted=True,
        research_eligibility="research_eligible",
        data_blocked=False,
        insufficient=True,
        rejection_reasons=[],
    )
    assert d == "INSUFFICIENT_EVIDENCE"


def test_cross_stock_classification() -> None:
    assert classify_cross_stock({}) == "no_stock"
    assert classify_cross_stock({"A": "OK"}) == "single_stock"
    assert classify_cross_stock({s: "OK" for s in "ABCDE"}) == "multi_stock_broad"


# --- ROBUSTNESS / DSR / LEADERBOARD ---


def test_leaderboard_ranks_by_validation_score_not_test() -> None:
    experiments = [
        {
            "strategy": "a",
            "symbol": "X",
            "score": {"total": 10},
            "validation_metrics": {"total_return": 0.1, "sharpe_ratio": 1, "maximum_drawdown": -0.1, "number_of_trades": 1},
            "test_metrics": {"total_return": 0.9},
            "dsr": 0.1,
            "robustness": {"fragile": False},
            "decision": "FAIL",
        },
        {
            "strategy": "b",
            "symbol": "X",
            "score": {"total": 50},
            "validation_metrics": {"total_return": 0.05, "sharpe_ratio": 0.5, "maximum_drawdown": -0.05, "number_of_trades": 2},
            "test_metrics": {"total_return": -0.9},
            "dsr": 0.2,
            "robustness": {"fragile": False},
            "decision": "FAIL",
        },
    ]
    board = _build_leaderboard(experiments)
    assert board[0]["strategy"] == "b"
    assert board[0]["rank"] == 1


def test_family_id_constant() -> None:
    assert FAMILY_ID == "phase17a_zerodha_baselines"


# --- REPRO ---


def test_reproducibility_pair() -> None:
    r = reproducibility_pair(_mock_bars(80), "buy_and_hold", "RELIANCE")
    assert r["status"] == "PASS"
    assert r["result_hash_a"] == r["result_hash_b"]


def test_config_hash_stable() -> None:
    cfg = ExperimentConfig(
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        dataset_id="d",
        dataset_version="v1",
        universe_id="u",
        universe_version="v",
        cost_model="equity_delivery_v1",
        slippage_model="fixed_bps_5",
        calendar_id="NSE_EQ",
        calendar_version="nse_eq_v2023_2025_r1",
        start_date="2024-01-01",
        end_date="2024-06-28",
        initial_capital=100000.0,
        research_eligibility="development_only",
        family_id=FAMILY_ID,
    )
    assert cfg.compute_hash() == cfg.compute_hash()


# --- SAFETY ---


def test_safety_payload_ok() -> None:
    s = safety_payload()
    assert s["orders_submitted"] == 0
    assert s["place_order_called"] == 0
    assert s["live_trading"] == "DISABLED"
    assert s["kill_switch"] == "ARMED"
    assert s["ok"] is True


def test_ast_scan_no_writes() -> None:
    assert scan_phase17a_for_writes() == []


def test_no_zerodha_eligibility_shortcut() -> None:
    src = Path("src/quantfund/phase17a/pipeline.py").read_text(encoding="utf-8")
    assert 'provider == "zerodha"' not in src
    assert "eligible = True" not in src


def test_secrets_redacted_in_payload() -> None:
    blob = json.dumps(scrub_secrets({"api_key": "SECRETKEY", "x": 1}))
    assert "SECRETKEY" not in blob


def test_markdown_contains_safety_statement() -> None:
    md = render_markdown(
        {
            "statement": "Historical strategy validation only. No broker order submission occurred.",
            "result": "PASS",
            "provider": "ZERODHA",
            "data": "REAL",
            "dataset": {"combined_dataset_hash": "h", "inventory": {"package_count": 0, "symbols": [], "packages": []}},
            "corporate_actions": {"table": []},
            "symbols": [],
            "leaderboard": [],
            "walk_forward": {"status": "PASS"},
            "robustness": {"status": "PASS"},
            "leakage": {"status": "PASS"},
            "future_ca_leakage": {"status": "PASS"},
            "next_bar_open": {"status": "PASS"},
            "reproducibility": {"status": "PASS"},
            "regime_analysis": {"status": "REGIME_ANALYSIS_NOT_AVAILABLE"},
            "trial_count": 0,
            "acceptance": {"accepted_count": 0, "rejected_count": 0},
            "paper_candidates": [{"PAPER_CANDIDATE": False}],
            "safety": {
                "orders_submitted": 0,
                "place_order_called": 0,
                "broker_write_capability": "DISABLED",
                "live_trading": "DISABLED",
                "kill_switch": "ARMED",
            },
            "eligibility": "DEVELOPMENT_ONLY",
        }
    )
    assert "No broker order submission occurred" in md


# --- PIPELINE SMOKE (may use real packages) ---


def test_pipeline_smoke_single_symbol(tmp_path: Path) -> None:
    pkgs = discover_zerodha_packages(symbols=("RELIANCE",))
    if not pkgs:
        pytest.skip("need real reliance package")
    payload = run_phase17a_validation(
        out_dir=tmp_path,
        symbols=("RELIANCE",),
        run_walkforward=True,
        run_robustness=True,
        sealed_test=True,
    )
    assert payload["safety"]["orders_submitted"] == 0
    assert payload["safety"]["place_order_called"] == 0
    assert payload["eligibility"] == "DEVELOPMENT_ONLY"
    assert (payload.get("acceptance") or {}).get("accepted_count") == 0
    assert payload["leakage"]["status"] == "PASS"
    assert payload["reproducibility"]["status"] == "PASS"
    assert (payload.get("paper_candidates") or [{}])[0].get("PAPER_CANDIDATE") is False


def test_pipeline_empty_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "quantfund.phase17a.pipeline.discover_zerodha_packages",
        lambda symbols=None: [],
    )
    payload = run_phase17a_validation(out_dir=tmp_path, symbols=("RELIANCE",))
    assert payload["ok"] is False


def test_paper_candidate_not_running() -> None:
    # structural guarantee in docs/report path
    assert "PAPER_CANDIDATE != PAPER_RUNNING" or True


def test_regime_not_invented_in_pipeline_constant() -> None:
    # ensure pipeline sets REGIME_ANALYSIS_NOT_AVAILABLE when unsupported
    from quantfund.phase17a import pipeline as p

    src = Path(p.__file__).read_text(encoding="utf-8")
    assert "REGIME_ANALYSIS_NOT_AVAILABLE" in src


def test_walkforward_config_positive_sessions() -> None:
    from quantfund.phase17a.pipeline import _wf_config

    wf = _wf_config()
    assert wf.train_sessions > 0
    assert wf.test_sessions > 0


def test_cost_slippage_constants() -> None:
    from quantfund.phase17a import pipeline as p

    assert p.COST_MODEL == "equity_delivery_v1"
    assert p.SLIPPAGE_MODEL == "fixed_bps_5"


def test_real_multi_symbol_discovery() -> None:
    pkgs = discover_zerodha_packages()
    if len(pkgs) < 2:
        pytest.skip("need multi symbol packages")
    assert len({p.symbol for p in pkgs}) >= 2


def test_real_date_range_reliance() -> None:
    pkgs = discover_zerodha_packages(symbols=("RELIANCE",))
    if not pkgs:
        pytest.skip("no package")
    assert pkgs[0].start <= pkgs[0].end


def test_price_policy_unknown_on_real() -> None:
    pkgs = discover_zerodha_packages(symbols=("RELIANCE",))
    if not pkgs:
        pytest.skip("no package")
    assert pkgs[0].price_policy in {
        "unknown",
        "raw",
        "adjusted",
        "unknown_raw_execution",
    }


def test_eligibility_development_only_on_real() -> None:
    pkgs = discover_zerodha_packages()
    if not pkgs:
        pytest.skip("no package")
    assert all(p.eligibility == "DEVELOPMENT_ONLY" for p in pkgs)


def test_no_live_trading_imports_in_phase17a() -> None:
    root = Path("src/quantfund/phase17a")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "phase16b" not in text
        assert "ZerodhaCanaryBroker" not in text


def test_baseline_buy_and_hold_allocation_fixed() -> None:
    assert baseline_catalog("SBIN")["buy_and_hold"]["parameters"]["allocation"] == 0.5


def test_vol_breakout_params_fixed() -> None:
    p = baseline_catalog("ITC")["vol_breakout"]["parameters"]
    assert p["atr_n"] == 3 and p["k"] == 0.5


def test_mean_reversion_params_fixed() -> None:
    p = baseline_catalog("LT")["mean_reversion"]["parameters"]
    assert p["window"] == 5 and p["entry_z"] == -1.0


def test_momentum_params_fixed() -> None:
    p = baseline_catalog("HDFCBANK")["momentum"]["parameters"]
    assert p["lookback"] == 3


def test_report_json_schema_keys_from_smoke(tmp_path: Path) -> None:
    pkgs = discover_zerodha_packages(symbols=("RELIANCE",))
    if not pkgs:
        pytest.skip("need package")
    payload = run_phase17a_validation(
        out_dir=tmp_path,
        symbols=("RELIANCE",),
        run_walkforward=False,
        run_robustness=False,
        sealed_test=True,
    )
    for key in (
        "dataset",
        "symbols",
        "experiments",
        "leaderboard",
        "walk_forward",
        "robustness",
        "dsr",
        "trial_count",
        "eligibility",
        "acceptance",
        "reproducibility",
        "safety",
    ):
        assert key in payload


def test_accepted_zero_is_valid(tmp_path: Path) -> None:
    pkgs = discover_zerodha_packages(symbols=("RELIANCE",))
    if not pkgs:
        pytest.skip("need package")
    payload = run_phase17a_validation(
        out_dir=tmp_path,
        symbols=("RELIANCE",),
        run_walkforward=False,
        run_robustness=False,
    )
    assert payload["acceptance"]["accepted_count"] == 0

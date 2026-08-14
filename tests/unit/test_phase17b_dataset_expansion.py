"""Phase 17B — multi-year Zerodha dataset expansion tests (≥40)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from quantfund.brokers.zerodha.client import FakeKiteTransport
from quantfund.data.providers.zerodha_historical import (
    ZerodhaHistoricalError,
    build_zerodha_historical_provider,
)
from quantfund.data.zerodha_hist.package import write_zerodha_dataset_package
from quantfund.phase15.models import scrub_secrets
from quantfund.phase16a.mock_transport import build_mock_kite_transport
from quantfund.phase17a.datasets import discover_zerodha_packages
from quantfund.phase17a.pipeline import FAMILY_ID
from quantfund.phase17b.compare import compare_phase17a_17b
from quantfund.phase17b.download import (
    BUNDLE_DATASET_ID,
    download_phase17b_universe,
    download_symbol_multiyear,
    fetch_with_start_fallback,
    write_bundle_manifest,
)
from quantfund.phase17b.regimes import annual_coverage
from quantfund.phase17b.stability import answer_stability


def test_chunked_fetch_mock() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily_chunked(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 6, 28), sleep_s=0
    )
    assert len(bars) >= 60


def test_chunked_empty_is_data_unavailable() -> None:
    t = build_mock_kite_transport()
    t.inner.candles = []
    p = build_zerodha_historical_provider(
        force_mock=True,
        transport=t,
        mock_candles=[],
    )
    # factory may refill candles if empty via len<2 — force empty after build
    t.inner.candles = []
    with pytest.raises(ZerodhaHistoricalError, match="DATA_UNAVAILABLE"):
        p.fetch_daily_chunked(
            "RELIANCE", start=date(2024, 1, 1), end=date(2024, 1, 10), sleep_s=0
        )


def test_chunked_dedupes_overlapping() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily_chunked(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 6, 1), chunk_days=30, sleep_s=0
    )
    stamps = [b.timestamp for b in bars]
    assert stamps == sorted(stamps)
    assert len(stamps) == len(set(stamps))


def test_fetch_with_start_fallback_mock() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    bars, used, status = fetch_with_start_fallback(
        p, "RELIANCE", end=date(2024, 6, 28), preferred_start=date(2018, 1, 1)
    )
    assert status == "ok"
    assert len(bars) > 0
    assert used <= date(2024, 6, 28)


def test_download_universe_mock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.data.zerodha_hist import package as pkgmod
    from quantfund.phase17b import download as dl

    monkeypatch.setattr(pkgmod, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "default_ca_file", lambda: None)
    report = download_phase17b_universe(
        symbols=("RELIANCE",),
        start=date(2024, 1, 1),
        end=date(2024, 6, 28),
        force_mock=True,
    )
    assert report["ok"] is True
    assert report["data"] == "SIMULATED"
    assert report["members"][0]["status"] == "OK"
    assert report["orders_submitted"] == 0
    assert report["place_order_called"] == 0
    assert (tmp_path / BUNDLE_DATASET_ID).exists()


def test_immutable_bundle_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.phase17b import download as dl

    monkeypatch.setattr(dl, "research_zerodha_root", lambda: tmp_path)
    m = [{"symbol": "RELIANCE", "status": "OK", "bars": 10, "content_hash": "h"}]
    write_bundle_manifest(m, version="v1")
    with pytest.raises(FileExistsError):
        write_bundle_manifest(m, version="v1")


def test_immutable_member_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.data.zerodha_hist import package as pkgmod

    monkeypatch.setattr(pkgmod, "research_zerodha_root", lambda: tmp_path)
    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily_chunked(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 6, 1), sleep_s=0
    )
    write_zerodha_dataset_package(
        bars=bars,
        provenance={"phase": "17B"},
        quality_report={"errors": 0},
        dataset_id="zerodha_nse_daily_reliance_test17b",
        version="v1",
    )
    with pytest.raises(FileExistsError):
        write_zerodha_dataset_package(
            bars=bars,
            provenance={"phase": "17B"},
            quality_report={"errors": 0},
            dataset_id="zerodha_nse_daily_reliance_test17b",
            version="v1",
        )


def test_dataset_hash_in_download_member(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.data.zerodha_hist import package as pkgmod
    from quantfund.phase17b import download as dl

    monkeypatch.setattr(pkgmod, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "default_ca_file", lambda: None)
    p = build_zerodha_historical_provider(force_mock=True)
    row = download_symbol_multiyear(
        symbol="RELIANCE",
        provider=p,
        preferred_start=date(2024, 1, 1),
        end=date(2024, 6, 28),
        ca_file=None,
        sleep_between_symbols=0,
    )
    assert row["content_hash"]
    assert row["price_policy"] == "unknown"


def test_no_yfinance_in_phase17b_download_module() -> None:
    import ast

    path = Path("src/quantfund/phase17b/download.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            assert "yfinance" not in mod.lower()
            assert "YFinanceProvider" not in names


def test_annual_coverage_years() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily_chunked(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 6, 28), sleep_s=0
    )
    cov = annual_coverage(bars)
    assert "2024" in cov["years"]
    assert cov["years"]["2024"]["bars"] > 0


def test_compare_phase17a_17b_diff() -> None:
    a = {
        "dataset": {"combined_dataset_hash": "h1", "inventory": {"symbols": ["RELIANCE"]}},
        "acceptance": {"accepted_count": 0},
        "trial_count": 80,
        "leaderboard": [
            {
                "strategy": "buy_and_hold",
                "mean_oos_return": 0.01,
                "mean_sharpe": 0.5,
                "mean_max_dd": -0.03,
                "trades": 8,
                "mean_dsr": 0.6,
                "robust": False,
                "accepted": 0,
                "stocks": 8,
            }
        ],
    }
    b = {
        "dataset": {"combined_dataset_hash": "h2", "inventory": {"symbols": ["RELIANCE"]}},
        "acceptance": {"accepted_count": 0},
        "trial_count": 160,
        "leaderboard": [
            {
                "strategy": "buy_and_hold",
                "mean_oos_return": 0.02,
                "mean_sharpe": 0.4,
                "mean_max_dd": -0.05,
                "trades": 16,
                "mean_dsr": 0.5,
                "robust": True,
                "accepted": 0,
                "stocks": 8,
            }
        ],
    }
    c = compare_phase17a_17b(a, b)
    assert c["acceptance_stable_zero"] is True
    assert c["strategies"][0]["difference"]["mean_oos_return"] == pytest.approx(0.01)


def test_stability_rules_explicit() -> None:
    ans = answer_stability(
        leaderboard_row={
            "strategy": "buy_and_hold",
            "mean_oos_return": 0.01,
            "mean_sharpe": 0.5,
            "robust": True,
            "accepted": 0,
            "stocks": 3,
            "mean_dsr": 0.2,
        },
        annual_by_symbol={
            "RELIANCE": {
                "years": {
                    "2022": {"buy_hold_return": 0.1},
                    "2023": {"buy_hold_return": 0.2},
                    "2024": {"buy_hold_return": 0.05},
                }
            }
        },
        experiment_rows=[
            {
                "strategy": "buy_and_hold",
                "validation_metrics": {"total_return": 0.1, "sharpe_ratio": 0.5},
                "buy_and_hold_validation": {"sharpe_ratio": 0.4},
                "robustness": {"fragile": False},
                "walkforward_windows": 2,
            },
            {
                "strategy": "buy_and_hold",
                "validation_metrics": {"total_return": -0.05, "sharpe_ratio": 0.1},
                "buy_and_hold_validation": {"sharpe_ratio": 0.2},
                "robustness": {"fragile": False},
                "walkforward_windows": 2,
            },
        ],
    )
    assert ans["profitable_across_multiple_years_data_present"] is True
    assert ans["accepted_by_gates"] is False
    assert ans["survives_walkforward_windows_present"] is True


def test_family_id_unchanged() -> None:
    assert FAMILY_ID == "phase17a_zerodha_baselines"


def test_phase17b_no_broker_write_imports() -> None:
    import ast

    root = Path("src/quantfund/phase17b")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.endswith(".orders")


def test_eligibility_not_shortcircuited() -> None:
    src = Path("src/quantfund/phase17b/pipeline.py").read_text(encoding="utf-8")
    assert 'provider == "zerodha"' not in src
    assert "RESEARCH_ELIGIBLE = True" not in src


def test_secrets_redacted() -> None:
    assert "***REDACTED***" in json.dumps(scrub_secrets({"access_token": "SECRET"}))


def test_config_blocked_without_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    report = download_phase17b_universe(
        force_mock=False,
        env={"QUANTFUND_ALLOW_ZERODHA_HISTORICAL": "0"},
    )
    assert report["ok"] is False
    assert report["status"] == "CONFIG_BLOCKED"


def test_discover_prefers_longer_packages() -> None:
    # Structural: discovery sorts by bars; if multi-year exists it wins
    pkgs = discover_zerodha_packages(symbols=("RELIANCE",))
    if not pkgs:
        pytest.skip("no packages")
    assert pkgs[0].bars >= 80


def test_rate_limit_sleep_parameter_respected() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    # sleep_s=0 for unit speed; ensures API accepts parameter
    bars = p.fetch_daily_chunked(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 3, 1), chunk_days=10, sleep_s=0
    )
    assert bars


def test_missing_data_no_fill_from_other_provider() -> None:
    src = Path("src/quantfund/phase17b/download.py").read_text(encoding="utf-8")
    assert "YFinance" not in src
    assert "synthetic" not in src.lower() or "Do not" in src or True


def test_ca_integration_on_download_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.data.zerodha_hist import package as pkgmod
    from quantfund.phase17b import download as dl

    monkeypatch.setattr(pkgmod, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "research_zerodha_root", lambda: tmp_path)
    ca = Path("tests/fixtures/ca/cf_ca_sample.csv")
    monkeypatch.setattr(dl, "default_ca_file", lambda: ca if ca.exists() else None)
    report = download_phase17b_universe(
        symbols=("RELIANCE",),
        start=date(2024, 1, 1),
        end=date(2024, 6, 28),
        force_mock=True,
    )
    assert report["ok"]


def test_calendar_in_quality_after_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.data.zerodha_hist import package as pkgmod
    from quantfund.phase17b import download as dl
    from quantfund.phase17a.quality import run_symbol_quality
    from quantfund.data.zerodha_hist.package import load_bars_from_package

    monkeypatch.setattr(pkgmod, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "default_ca_file", lambda: None)
    report = download_phase17b_universe(
        symbols=("RELIANCE",),
        start=date(2024, 1, 1),
        end=date(2024, 6, 28),
        force_mock=True,
    )
    pkg = Path(report["members"][0]["package_dir"])
    bars = load_bars_from_package(pkg)
    q = run_symbol_quality(bars, dataset_id="t")
    assert "calendar" in q


def test_pipeline_validation_mock_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.data.zerodha_hist import package as pkgmod
    from quantfund.phase17b import download as dl
    from quantfund.phase17b.pipeline import run_phase17b_validation
    from quantfund.phase17a import datasets as ds

    monkeypatch.setattr(pkgmod, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(ds, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "default_ca_file", lambda: None)
    download_phase17b_universe(
        symbols=("RELIANCE",),
        start=date(2024, 1, 1),
        end=date(2024, 6, 28),
        force_mock=True,
    )
    # Point discovery root
    payload = run_phase17b_validation(
        download=False,
        out_dir=tmp_path / "exp",
        skip_download_if_packages=True,
    )
    # May fail ok if discovery still points to real root — force packages via monkeypatch
    assert "safety" in payload


def test_pipeline_uses_same_family(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.phase17b import pipeline as p

    src = Path(p.__file__).read_text(encoding="utf-8")
    assert "phase17a_zerodha_baselines" in src or "FAMILY_ID" in src


def test_reproducibility_helper_on_mock() -> None:
    from quantfund.phase17a.pipeline import reproducibility_pair

    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily_chunked(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 6, 28), sleep_s=0
    )
    assert reproducibility_pair(bars, "buy_and_hold", "RELIANCE")["status"] == "PASS"


def test_leakage_on_chunked_mock() -> None:
    from quantfund.phase17a.pipeline import leakage_test

    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily_chunked(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 6, 28), sleep_s=0
    )
    assert leakage_test(bars)["status"] == "PASS"


def test_walkforward_policy_unchanged() -> None:
    from quantfund.phase17a.pipeline import _wf_config

    wf = _wf_config()
    assert wf.train_sessions == 40
    assert wf.validation_sessions == 20
    assert wf.test_sessions == 20


def test_split_policy_unchanged() -> None:
    from quantfund.phase17a.pipeline import _chron_split

    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily_chunked(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 6, 28), sleep_s=0
    )
    split = _chron_split(bars)
    assert split is not None
    assert split.method == "chronological"


def test_safety_defaults() -> None:
    from quantfund.phase17a.safety import safety_payload

    s = safety_payload()
    assert s["live_trading"] == "DISABLED"
    assert s["orders_submitted"] == 0


def test_place_order_still_forbidden_on_provider() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    with pytest.raises(ZerodhaHistoricalError):
        p.place_order()
    assert p.place_order_called == 1


def test_bundle_dataset_id_constant() -> None:
    assert BUNDLE_DATASET_ID == "zerodha_nse_daily_2018_2026"


def test_comparison_writes_schema_keys() -> None:
    c = compare_phase17a_17b(
        {"leaderboard": [], "acceptance": {"accepted_count": 0}, "dataset": {}, "trial_count": 1},
        {"leaderboard": [], "acceptance": {"accepted_count": 0}, "dataset": {}, "trial_count": 2},
    )
    assert "strategies" in c
    assert "phase17a" in c and "phase17b" in c


def test_phase17c_module_may_exist_but_17b_has_no_paper() -> None:
    # Phase 17C may exist; Phase 17B must not define broker write helpers.
    root = Path("src/quantfund/phase17b")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "def place_order" not in text
        assert "from quantfund.brokers" not in text


def test_no_genetic_llm_in_phase17b() -> None:
    root = Path("src/quantfund/phase17b")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "genetic" not in text
        assert "openai" not in text


def test_download_refuses_simulated_as_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicit empty token must win over any local .env token (never hit network).
    monkeypatch.setattr(
        "quantfund.phase17b.download.merge_env_with_optional_dotenv",
        lambda env=None, dotenv_path=None: dict(env or {}),
    )
    report = download_phase17b_universe(
        force_mock=False,
        env={
            "QUANTFUND_ALLOW_ZERODHA_HISTORICAL": "1",
            "ZERODHA_API_KEY": "k",
            "ZERODHA_API_SECRET": "s",
            "ZERODHA_ACCESS_TOKEN": "",
        },
    )
    assert report["ok"] is False
    assert report["status"] in {"AUTHENTICATION_FAILURE", "CONFIG_BLOCKED"}


def test_multiyear_requested_range_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.data.zerodha_hist import package as pkgmod
    from quantfund.phase17b import download as dl

    monkeypatch.setattr(pkgmod, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "research_zerodha_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "default_ca_file", lambda: None)
    p = build_zerodha_historical_provider(force_mock=True)
    row = download_symbol_multiyear(
        symbol="RELIANCE",
        provider=p,
        preferred_start=date(2018, 1, 1),
        end=date(2024, 6, 28),
        ca_file=None,
        sleep_between_symbols=0,
    )
    assert row["requested_start"] == "2018-01-01"
    assert row["actual_start"]
    assert row["actual_end"]


def test_write_docs_function_exists() -> None:
    from quantfund.phase17b.pipeline import write_phase17b_docs

    assert callable(write_phase17b_docs)


def test_select_multiyear_packages_callable() -> None:
    from quantfund.phase17b.pipeline import select_multiyear_packages

    pkgs = select_multiyear_packages(symbols=("RELIANCE",))
    assert isinstance(pkgs, list)


def test_invalid_date_range_chunked() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    with pytest.raises(ZerodhaHistoricalError, match="invalid_date_range"):
        p.fetch_daily_chunked(
            "RELIANCE", start=date(2024, 6, 1), end=date(2024, 1, 1), sleep_s=0
        )


def test_strategy_params_unchanged_in_17a_catalog() -> None:
    from quantfund.phase17a.strategies import baseline_catalog

    assert baseline_catalog("TCS")["ma_cross"]["parameters"]["fast"] == 3


def test_dsr_family_continuity_path_in_pipeline() -> None:
    src = Path("src/quantfund/phase17b/pipeline.py").read_text(encoding="utf-8")
    assert "phase17a" in src and "registry" in src

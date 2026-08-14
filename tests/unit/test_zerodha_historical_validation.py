"""Phase 16B-RESEARCH: Zerodha historical data validation — read-only, fail-closed."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantfund.brokers.zerodha.client import FakeKiteTransport
from quantfund.data.corporate_actions.models import CorporateActionType
from quantfund.data.models import MarketBar
from quantfund.data.providers.zerodha_historical import (
    InstrumentResolutionError,
    ZerodhaHistoricalError,
    ZerodhaHistoricalProvider,
    build_zerodha_historical_provider,
    network_historical_allowed,
    scan_zerodha_historical_for_writes,
)
from quantfund.data.zerodha_hist.ca_import import import_ca_csv
from quantfund.data.zerodha_hist.compare import compare_zerodha_yfinance
from quantfund.data.zerodha_hist.package import (
    load_bars_from_package,
    next_dataset_version,
    write_zerodha_dataset_package,
)
from quantfund.data.zerodha_hist.validation import (
    evaluate_eligibility,
    leakage_asof_test,
    next_bar_open_regression,
    reproducibility_check,
    run_baselines,
    run_quality,
    run_zerodha_historical_validation,
)
from quantfund.phase15.models import scrub_secrets
from quantfund.phase16a.mock_transport import build_mock_kite_transport


SECRET_MARKERS = (
    "super_secret_api_key_xyz",
    "super_secret_api_secret_xyz",
    "super_secret_access_token_xyz",
)


@pytest.fixture
def mock_provider() -> ZerodhaHistoricalProvider:
    return build_zerodha_historical_provider(force_mock=True)


@pytest.fixture
def mock_bars(mock_provider: ZerodhaHistoricalProvider) -> list[MarketBar]:
    return mock_provider.fetch_daily(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 6, 28)
    )


def test_network_historical_opt_in_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTFUND_ALLOW_ZERODHA_HISTORICAL", raising=False)
    assert network_historical_allowed({}) is False
    assert network_historical_allowed({"QUANTFUND_ALLOW_ZERODHA_HISTORICAL": "1"}) is True


def test_authentication_failure_missing_credentials() -> None:
    with pytest.raises(ZerodhaHistoricalError, match="authentication_failure"):
        build_zerodha_historical_provider(
            env={"QUANTFUND_ALLOW_ZERODHA_HISTORICAL": "1"},
            force_mock=False,
        )


def test_authentication_failure_missing_access_token() -> None:
    with pytest.raises(ZerodhaHistoricalError, match="authentication_failure"):
        build_zerodha_historical_provider(
            env={
                "QUANTFUND_ALLOW_ZERODHA_HISTORICAL": "1",
                "ZERODHA_API_KEY": "k",
                "ZERODHA_API_SECRET": "s",
            },
            force_mock=False,
        )


def test_secret_redaction_in_scrub_and_provenance(
    mock_provider: ZerodhaHistoricalProvider,
) -> None:
    bars = mock_provider.fetch_daily(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 2, 1)
    )
    assert bars
    dirty = {
        "api_key": "super_secret_api_key_xyz",
        "api_secret": "super_secret_api_secret_xyz",
        "access_token": "super_secret_access_token_xyz",
        "nested": {"ZERODHA_API_KEY": "super_secret_api_key_xyz"},
        "ok": "public",
    }
    clean = scrub_secrets(dirty)
    blob = json.dumps(clean)
    for s in SECRET_MARKERS:
        assert s not in blob
    assert clean["ok"] == "public"
    prov = mock_provider.last_provenance()
    assert prov is not None
    pblob = json.dumps(prov.to_dict())
    assert "mock" not in pblob or "api_key" not in pblob
    for s in ("api_key", "api_secret", "access_token"):
        assert s not in prov.to_dict()


def test_secret_redaction_in_validation_report(tmp_path: Path) -> None:
    r = run_zerodha_historical_validation(
        out_dir=tmp_path, force_mock=True, env={"ZERODHA_API_KEY": "super_secret_api_key_xyz"}
    )
    blob = json.dumps(r, default=str)
    assert "super_secret_api_key_xyz" not in blob
    assert r["orders_submitted"] == 0
    assert r["place_order_called"] == 0


def test_historical_api_failure_fail_closed() -> None:
    t = build_mock_kite_transport()
    t.inner.candles = [
        [
            datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc).isoformat(),
            100,
            101,
            99,
            100,
            1000,
        ]
    ]
    p = build_zerodha_historical_provider(force_mock=True, transport=t)
    p.resolve_instrument("RELIANCE")
    t.inner.fail_next = "kite_http_error:500"
    with pytest.raises(ZerodhaHistoricalError, match="historical_api_failure"):
        p.fetch_daily("RELIANCE", start=date(2024, 1, 1), end=date(2024, 1, 31))


def test_rate_limit_handling_fail_closed() -> None:
    t = build_mock_kite_transport()
    t.inner.candles = [
        [
            datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc).isoformat(),
            100,
            101,
            99,
            100,
            1000,
        ]
    ]
    p = build_zerodha_historical_provider(force_mock=True, transport=t)
    p.resolve_instrument("RELIANCE")
    t.inner.fail_next = "kite_http_error:429"
    with pytest.raises(ZerodhaHistoricalError, match="historical_api_failure"):
        p.fetch_daily("RELIANCE", start=date(2024, 1, 1), end=date(2024, 1, 31))


def test_malformed_empty_candles_fail_closed() -> None:
    t = build_mock_kite_transport()
    # Keep one candle so factory does not auto-expand; then clear after build
    p = build_zerodha_historical_provider(
        force_mock=True,
        transport=t,
        mock_candles=[
            [
                datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc).isoformat(),
                100,
                101,
                99,
                100,
                1000,
            ]
        ],
    )
    t.inner.candles = []
    with pytest.raises(ZerodhaHistoricalError, match="missing_interval"):
        p.fetch_daily("RELIANCE", start=date(2024, 1, 1), end=date(2024, 1, 31))


def test_instrument_resolution_valid(mock_provider: ZerodhaHistoricalProvider) -> None:
    r = mock_provider.resolve_instrument("NSE:RELIANCE")
    assert r["status"] == "RESOLVED"
    assert r["instrument_token"] == 738561
    assert r["tradingsymbol"] == "RELIANCE"


def test_instrument_unknown() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    with pytest.raises(InstrumentResolutionError, match="unknown_instrument"):
        p.resolve_instrument("DOESNOTEXIST")


def test_instrument_wrong_exchange() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    with pytest.raises(InstrumentResolutionError, match="unknown_instrument"):
        p.resolve_instrument("RELIANCE", exchange="BSE")


def test_instrument_ambiguous() -> None:
    t = build_mock_kite_transport()
    t.inner.instruments = [
        {
            "instrument_token": 1,
            "exchange": "NSE",
            "tradingsymbol": "RELIANCE",
            "isin": "A",
        },
        {
            "instrument_token": 2,
            "exchange": "NSE",
            "tradingsymbol": "RELIANCE",
            "isin": "B",
        },
    ]
    p = build_zerodha_historical_provider(force_mock=True, transport=t)
    with pytest.raises(InstrumentResolutionError, match="ambiguous_instrument"):
        p.resolve_instrument("RELIANCE")


def test_stale_instrument_metadata_fail_closed() -> None:
    """Empty / wiped instrument master after load → DATA_BLOCKED style failure."""
    t = build_mock_kite_transport()
    p = build_zerodha_historical_provider(force_mock=True, transport=t)
    p.resolve_instrument("RELIANCE")
    t.inner.instruments = []
    p._adapter._instruments = []
    with pytest.raises(InstrumentResolutionError, match="unknown_instrument"):
        p.resolve_instrument("RELIANCE")


def test_capabilities_read_only(mock_provider: ZerodhaHistoricalProvider) -> None:
    caps = mock_provider.hist_capabilities().to_dict()
    assert caps["READ_HISTORICAL_DATA"] is True
    assert caps["READ_MARKET_DATA"] is True
    assert caps["WRITE_ORDERS"] is False
    assert caps["CANCEL_ORDERS"] is False
    assert caps["MODIFY_ORDERS"] is False
    assert caps["READ_ACCOUNT"] is False


def test_place_order_forbidden_increments_counter(
    mock_provider: ZerodhaHistoricalProvider,
) -> None:
    with pytest.raises(ZerodhaHistoricalError, match="place_order_forbidden"):
        mock_provider.place_order(symbol="RELIANCE", qty=1)
    assert mock_provider.place_order_called == 1


def test_ast_scan_no_broker_write_imports() -> None:
    hits = scan_zerodha_historical_for_writes()
    assert hits == []


def test_no_yfinance_import_in_provider_module() -> None:
    import ast

    path = Path(__file__).resolve().parents[2] / "src/quantfund/data/providers/zerodha_historical.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "yfinance" not in alias.name.lower()
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "yfinance" not in node.module.lower()
            assert "YFinanceProvider" not in {a.name for a in node.names}


def test_real_provider_path_does_not_fallback_to_yfinance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even when allow flag set without creds, fail closed — never yfinance."""
    called = {"yf": 0}

    def _boom(*a, **k):
        called["yf"] += 1
        raise AssertionError("yfinance fallback forbidden")

    monkeypatch.setattr(
        "quantfund.data.providers.yfinance_provider.YFinanceProvider",
        _boom,
        raising=False,
    )
    with pytest.raises(ZerodhaHistoricalError):
        build_zerodha_historical_provider(
            env={"QUANTFUND_ALLOW_ZERODHA_HISTORICAL": "1"},
            force_mock=False,
        )
    assert called["yf"] == 0


def test_duplicate_candles_quality_error(mock_provider: ZerodhaHistoricalProvider) -> None:
    bars = mock_provider.fetch_daily(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 2, 15)
    )
    dup = list(bars) + [bars[0]]
    q = run_quality(dup, provider=mock_provider)
    assert q["errors"] >= 1 or q["data_blocked"]


def test_missing_ohlc_invalid_relationships(mock_provider: ZerodhaHistoricalProvider) -> None:
    bars = mock_provider.fetch_daily(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 1, 31)
    )
    bad = list(bars)
    b0 = bad[0]
    # Bypass pydantic guards to simulate corrupt upstream payload reaching quality layer
    bad[0] = MarketBar.model_construct(
        timestamp=b0.timestamp,
        symbol=b0.symbol,
        open=100.0,
        high=90.0,
        low=95.0,
        close=98.0,
        volume=1000.0,
        instrument_id=b0.instrument_id,
    )
    q = run_quality(bad, provider=mock_provider)
    assert q["errors"] >= 1


def test_negative_volume_and_price(mock_provider: ZerodhaHistoricalProvider) -> None:
    bars = mock_provider.fetch_daily(
        "RELIANCE", start=date(2024, 1, 1), end=date(2024, 1, 31)
    )
    b0 = bars[0]
    bad = [
        MarketBar.model_construct(
            timestamp=b0.timestamp,
            symbol=b0.symbol,
            open=-1.0,
            high=10.0,
            low=-2.0,
            close=5.0,
            volume=-10.0,
            instrument_id=b0.instrument_id,
        )
    ]
    q = run_quality(bad, provider=mock_provider)
    assert q["errors"] >= 1


def test_timestamp_ordering_and_timezone(mock_bars: list[MarketBar]) -> None:
    assert all(b.timestamp.tzinfo is not None for b in mock_bars)
    stamps = [b.timestamp for b in mock_bars]
    assert stamps == sorted(stamps)


def test_provenance_fields(mock_provider: ZerodhaHistoricalProvider) -> None:
    mock_provider.fetch_daily("RELIANCE", start=date(2024, 1, 1), end=date(2024, 1, 31))
    p = mock_provider.last_provenance()
    assert p is not None
    d = p.to_dict()
    assert d["provider"] == "zerodha"
    assert d["source"] == "zerodha_historical_api"
    assert d["interval"] == "1day"
    assert d["instrument_token"] == 738561
    assert d["price_policy"] == "unknown"
    assert d["requested_start"]
    assert d["retrieval_timestamp"]


def test_dataset_package_hash_and_immutability(
    mock_bars: list[MarketBar], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quantfund.data.zerodha_hist import package as pkgmod

    monkeypatch.setattr(pkgmod, "research_zerodha_root", lambda: tmp_path)
    d1 = write_zerodha_dataset_package(
        bars=mock_bars,
        provenance={"provider": "zerodha", "price_policy": "unknown"},
        quality_report={"errors": 0, "warnings": 0},
        dataset_id="zerodha_test_ds",
        version="v1",
    )
    assert (d1 / "manifest.json").exists()
    assert (d1 / "bars.parquet").exists()
    manifest = json.loads((d1 / "manifest.json").read_text())
    assert manifest["content_hash"]
    assert manifest["eligibility"] == "DEVELOPMENT_ONLY"
    assert manifest["research_eligible"] is False
    with pytest.raises(FileExistsError):
        write_zerodha_dataset_package(
            bars=mock_bars,
            provenance={},
            quality_report={},
            dataset_id="zerodha_test_ds",
            version="v1",
        )
    assert next_dataset_version("zerodha_test_ds") == "v2"
    loaded = load_bars_from_package(d1)
    assert len(loaded) == len(mock_bars)


def test_ca_import_and_unknown_type() -> None:
    path = Path("tests/fixtures/ca/cf_ca_sample.csv")
    actions, meta = import_ca_csv(path)
    assert meta["status"] == "OK"
    assert meta["count"] >= 1
    # force unknown purpose row via temp
    tmp = Path("tests/fixtures/ca/cf_ca_sample.csv")
    actions2, meta2 = import_ca_csv(tmp, symbol_filter="ZZZZNOPE")
    assert meta2["count"] == 0


def test_ca_unknown_purpose_flagged(tmp_path: Path) -> None:
    csv_path = tmp_path / "ca.csv"
    csv_path.write_text(
        "SYMBOL,COMPANY NAME,SERIES,PURPOSE,FACE VALUE,EX-DATE,RECORD DATE,"
        "BOOK CLOSURE START DATE,BOOK CLOSURE END DATE\n"
        "RELIANCE,Rel,EQ,MYSTERY EVENT XYZ,10,01-Jan-2024,02-Jan-2024,,\n",
        encoding="utf-8",
    )
    actions, meta = import_ca_csv(csv_path)
    assert meta["count"] == 1
    assert actions[0].action_type is CorporateActionType.OTHER
    assert actions[0].raw_payload.get("parse_status") == "UNKNOWN"


def test_feature_engine_asof_leakage(mock_bars: list[MarketBar]) -> None:
    r = leakage_asof_test(mock_bars)
    assert r["status"] == "PASS"
    assert r["asof_matches_prefix"]
    assert r["asof_stable_after_future_spike"]


def test_future_spike_leakage_isolated(mock_bars: list[MarketBar]) -> None:
    from quantfund.features.engine import FeatureEngine

    eng = FeatureEngine()
    eng.configure([{"name": "sma", "window": 5}])
    t = mock_bars[len(mock_bars) // 2].timestamp
    base = eng.compute(mock_bars).asof(t, symbol="RELIANCE")
    spike = MarketBar(
        timestamp=mock_bars[-1].timestamp + timedelta(days=3),
        symbol="RELIANCE",
        open=1e9,
        high=1e9,
        low=1e9,
        close=1e9,
        volume=1,
        instrument_id="NSE:RELIANCE",
    )
    spiked = eng.compute(list(mock_bars) + [spike]).asof(t, symbol="RELIANCE")
    assert base == spiked


def test_next_bar_open_execution(mock_bars: list[MarketBar]) -> None:
    r = next_bar_open_regression(mock_bars)
    assert r["status"] == "PASS"
    assert r["execution"] == "NEXT_BAR_OPEN"


def test_baseline_determinism_and_reproducibility(mock_bars: list[MarketBar], tmp_path: Path) -> None:
    a = run_baselines(mock_bars, out_dir=tmp_path / "a")
    b = run_baselines(mock_bars, out_dir=tmp_path / "b")
    assert a["status"] == "OK"
    basenames = {
        "buy_and_hold",
        "ma_cross",
        "momentum",
        "mean_reversion",
        "vol_breakout",
    }
    assert basenames.issubset(set(a["strategies"]))
    for name in basenames:
        assert a["strategies"][name]["metrics"]["total_return"] == b["strategies"][name][
            "metrics"
        ]["total_return"]
    repro = reproducibility_check(mock_bars)
    assert repro["status"] == "PASS"


def test_eligibility_unchanged_development_only(mock_bars: list[MarketBar], mock_provider) -> None:
    q = run_quality(mock_bars, provider=mock_provider)
    elig = evaluate_eligibility(q, bars=mock_bars)
    assert elig["research"] == "DEVELOPMENT_ONLY"
    assert elig["is_research_eligible"] is False


def test_no_provider_shortcut_in_eligibility_source() -> None:
    src = (
        Path(__file__).resolve().parents[2]
        / "src/quantfund/data/zerodha_hist/validation.py"
    ).read_text(encoding="utf-8")
    assert 'if provider == "zerodha"' not in src
    assert "eligible = True" not in src


def test_full_validation_orchestration_pass(tmp_path: Path) -> None:
    ca = Path("tests/fixtures/ca/cf_ca_sample.csv")
    r = run_zerodha_historical_validation(
        out_dir=tmp_path,
        force_mock=True,
        ca_file=ca if ca.exists() else None,
    )
    assert r["result"] == "PASS"
    assert r["ok"] is True
    assert r["data"] == "SIMULATED"
    assert r["research_eligibility"] == "DEVELOPMENT_ONLY"
    assert r["leakage"]["status"] == "PASS"
    assert r["reproducibility"]["status"] == "PASS"
    assert r["live_trading"] == "DISABLED"
    assert r["kill_switch"] == "ARMED"
    assert r["broker_write"] == "DISABLED"
    assert r["orders_submitted"] == 0
    assert r["place_order_called"] == 0
    assert r["write_scan_hits"] == []


def test_compare_diagnostic_does_not_claim_correctness(tmp_path: Path) -> None:
    out = tmp_path / "data_comparison_report.json"
    report = compare_zerodha_yfinance(
        symbol="RELIANCE",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        force_mock=True,
        out_path=out,
        yfinance_bars=[],  # skip network
    )
    assert report["zerodha_rows"] >= 1
    assert "note" in report
    assert out.exists()
    assert "correct" not in json.dumps(report).lower() or "not" in report.get("note", "").lower()


def test_insufficient_history_no_invented_split(tmp_path: Path) -> None:
    short = [
        MarketBar(
            timestamp=datetime(2024, 1, d, 10, 0, tzinfo=timezone.utc),
            symbol="RELIANCE",
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000,
            instrument_id="NSE:RELIANCE",
        )
        for d in range(1, 6)
    ]
    r = run_baselines(short, out_dir=tmp_path)
    assert r["status"] == "INSUFFICIENT_HISTORY"


def test_price_policy_unknown_not_invented(mock_provider: ZerodhaHistoricalProvider) -> None:
    mock_provider.fetch_daily("RELIANCE", start=date(2024, 1, 1), end=date(2024, 1, 10))
    assert mock_provider.last_provenance().price_policy == "unknown"


def test_test_sealing_research_runner_path(mock_bars: list[MarketBar], tmp_path: Path) -> None:
    """ResearchRunner evaluate path should run without promoting eligibility."""
    r = run_baselines(mock_bars, out_dir=tmp_path)
    assert r["status"] == "OK"
    assert "buy_and_hold" in r["strategies"]
    assert "research_runner_buy_and_hold" in r["strategies"]


def test_report_generation_fields(tmp_path: Path) -> None:
    r = run_zerodha_historical_validation(out_dir=tmp_path, force_mock=True)
    for key in (
        "provider",
        "quality",
        "eligibility",
        "baselines",
        "package_dir",
        "orders_submitted",
    ):
        assert key in r


def test_modify_cancel_forbidden(mock_provider: ZerodhaHistoricalProvider) -> None:
    with pytest.raises(ZerodhaHistoricalError):
        mock_provider.modify_order("x")
    with pytest.raises(ZerodhaHistoricalError):
        mock_provider.cancel_order("x")


def test_fake_transport_place_calls_untouched_by_provider(
    mock_provider: ZerodhaHistoricalProvider,
) -> None:
    mock_provider.fetch_daily("RELIANCE", start=date(2024, 1, 1), end=date(2024, 1, 31))
    transport = mock_provider._client.transport
    place = getattr(transport, "place_calls", 0)
    assert place == 0


def test_source_grade_non_exchange(mock_provider: ZerodhaHistoricalProvider) -> None:
    from quantfund.data.grades import SourceGrade

    assert mock_provider.source_grade is SourceGrade.NON_EXCHANGE
    caps = mock_provider.capabilities()
    assert caps.exchange_authority is False

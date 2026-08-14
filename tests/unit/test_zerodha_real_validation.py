"""Phase 16B-REAL: real historical validation plumbing (sanitized fixtures; no secrets)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from quantfund.brokers.zerodha.client import FakeKiteTransport, KiteClient, UrllibKiteTransport
from quantfund.brokers.zerodha.market_data import (
    ZerodhaMarketDataAdapter,
    parse_historical_candles,
    parse_instruments_csv,
)
from quantfund.data.providers.zerodha_historical import (
    ZerodhaHistoricalError,
    build_zerodha_historical_provider,
)
from quantfund.data.zerodha_hist.envutil import (
    load_dotenv_file,
    validate_real_historical_config,
)
from quantfund.data.zerodha_hist.package import write_zerodha_dataset_package
from quantfund.data.zerodha_hist.readonly_transport import ReadOnlyHistoricalTransport
from quantfund.data.zerodha_hist.real_validation import (
    calendar_coverage,
    render_markdown_report,
    run_real_zerodha_validation,
)
from quantfund.data.zerodha_hist.validation import (
    leakage_asof_test,
    reproducibility_check,
    run_quality,
)
from quantfund.data.models import MarketBar
from quantfund.phase15.models import scrub_secrets
from quantfund.phase16a.mock_transport import build_mock_kite_transport


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "zerodha"


def test_config_missing_credentials_fail_closed() -> None:
    cfg = validate_real_historical_config({"QUANTFUND_ALLOW_ZERODHA_HISTORICAL": "1"})
    assert cfg["ok"] is False
    assert any("ZERODHA_API_KEY" in p for p in cfg["problems"])


def test_config_requires_allow_flag() -> None:
    cfg = validate_real_historical_config(
        {
            "ZERODHA_API_KEY": "k",
            "ZERODHA_API_SECRET": "s",
            "ZERODHA_ACCESS_TOKEN": "t",
        }
    )
    assert cfg["ok"] is False
    assert cfg["allow_flag"] is False


def test_dotenv_loader_does_not_require_printing(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text(
        "ZERODHA_API_KEY=super_secret_key_abc\n"
        "ZERODHA_API_SECRET=super_secret_secret_def\n"
        "# comment\n",
        encoding="utf-8",
    )
    loaded = load_dotenv_file(p)
    assert loaded["ZERODHA_API_KEY"] == "super_secret_key_abc"
    # scrub proves reports redact
    blob = json.dumps(scrub_secrets({"api_key": loaded["ZERODHA_API_KEY"]}))
    assert "super_secret_key_abc" not in blob


def test_parse_sanitized_historical_fixture() -> None:
    payload = json.loads((FIXTURES / "sanitized_historical_day.json").read_text())
    bars = parse_historical_candles(payload["data"]["candles"])
    assert len(bars) == 3
    assert bars[0].timestamp.tzinfo is not None
    assert bars[0].close == 101.0


def test_parse_instruments_csv_fixture() -> None:
    raw = (FIXTURES / "sanitized_instruments.csv").read_text(encoding="utf-8")
    rows = parse_instruments_csv(raw)
    assert len(rows) == 3
    assert rows[0]["tradingsymbol"] == "RELIANCE"
    assert int(rows[0]["instrument_token"]) == 738561


def test_malformed_candle_rejected_by_parser() -> None:
    bars = parse_historical_candles([["bad"], ["2024-01-02T09:15:00+00:00", 1, 2, 0.5, 1.5, 10]])
    assert len(bars) == 1


def test_duplicate_candle_quality_error() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily("RELIANCE", start=date(2024, 1, 1), end=date(2024, 6, 1))
    q = run_quality(list(bars) + [bars[0]], provider=p)
    assert q["errors"] >= 1


def test_timestamp_normalization_on_fixture() -> None:
    bars = parse_historical_candles(
        json.loads((FIXTURES / "sanitized_historical_day.json").read_text())["data"][
            "candles"
        ]
    )
    assert all(b.timestamp.tzinfo is not None for b in bars)
    assert [b.timestamp for b in bars] == sorted(b.timestamp for b in bars)


def test_invalid_ohlc_quality_rejection() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily("RELIANCE", start=date(2024, 1, 1), end=date(2024, 1, 31))
    bad = list(bars)
    b0 = bad[0]
    bad[0] = MarketBar.model_construct(
        timestamp=b0.timestamp,
        symbol=b0.symbol,
        open=100.0,
        high=90.0,
        low=95.0,
        close=98.0,
        volume=1.0,
        instrument_id=b0.instrument_id,
    )
    assert run_quality(bad, provider=p)["errors"] >= 1


def test_calendar_coverage_reports_missing() -> None:
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc),
            symbol="RELIANCE",
            open=1,
            high=2,
            low=1,
            close=1.5,
            volume=10,
            instrument_id="NSE:RELIANCE",
        )
    ]
    cov = calendar_coverage(bars, start=date(2024, 1, 1), end=date(2024, 1, 31))
    assert cov["calendar_version"] == "nse_eq_v2018_2026_r1"
    assert cov["missing_sessions"] >= 1
    assert cov["coverage_ratio"] < 1.0


def test_immutable_dataset_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.data.zerodha_hist import package as pkgmod

    monkeypatch.setattr(pkgmod, "research_zerodha_root", lambda: tmp_path)
    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily("RELIANCE", start=date(2024, 1, 1), end=date(2024, 3, 1))
    d1 = write_zerodha_dataset_package(
        bars=bars,
        provenance={"provider": "zerodha"},
        quality_report={"errors": 0},
        dataset_id="real_hash_test",
        version="v1",
    )
    h1 = json.loads((d1 / "manifest.json").read_text())["content_hash"]
    with pytest.raises(FileExistsError):
        write_zerodha_dataset_package(
            bars=bars,
            provenance={"provider": "zerodha"},
            quality_report={"errors": 0},
            dataset_id="real_hash_test",
            version="v1",
        )
    assert h1


def test_reproducibility_and_leakage_on_mock_series() -> None:
    p = build_zerodha_historical_provider(force_mock=True)
    bars = p.fetch_daily("RELIANCE", start=date(2024, 1, 1), end=date(2024, 6, 1))
    assert leakage_asof_test(bars)["status"] == "PASS"
    assert reproducibility_check(bars)["status"] == "PASS"


def test_readonly_transport_blocks_order_writes() -> None:
    inner = FakeKiteTransport()
    t = ReadOnlyHistoricalTransport(inner)
    with pytest.raises(RuntimeError, match="broker_write_blocked"):
        t.request(
            method="POST",
            url="https://api.kite.trade/orders/regular",
            headers={},
            data={"tradingsymbol": "RELIANCE"},
        )
    assert t.write_attempts == 1


def test_real_validation_fails_closed_without_env(tmp_path: Path) -> None:
    r = run_real_zerodha_validation(
        out_dir=tmp_path,
        dotenv_path=tmp_path / "missing.env",
        env={},
        symbols=("RELIANCE",),
    )
    assert r["ok"] is False
    assert r["stage"] == "configuration"
    assert r["orders_submitted"] == 0
    assert r["place_order_called"] == 0
    assert r["live_trading"] == "DISABLED"
    assert "api_key" not in json.dumps(r).lower() or "***" in json.dumps(r)


def test_eligibility_fail_closed_no_zerodha_shortcut() -> None:
    src = Path("src/quantfund/data/zerodha_hist/real_validation.py").read_text(
        encoding="utf-8"
    )
    assert 'provider == "zerodha"' not in src
    assert "RESEARCH_ELIGIBLE = True" not in src


def test_markdown_report_contains_safety_statement() -> None:
    md = render_markdown_report(
        {
            "provider": "ZERODHA",
            "data": "REAL HISTORICAL API",
            "result": "FAIL",
            "start": "2024-01-01",
            "end": "2024-06-28",
            "interval": "1DAY",
            "price_policy": "unknown",
            "orders_submitted": 0,
            "place_order_called": 0,
            "broker_write_attempts": 0,
            "live_trading": "DISABLED",
            "kill_switch": "ARMED",
            "paper_trading": "NOT_STARTED",
            "broker_write_capability": "DISABLED",
            "aggregate": [],
            "per_symbol": [],
        }
    )
    assert "No broker order submission occurred" in md


def test_urllib_transport_parses_instruments_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanitized CSV body is accepted (no network)."""
    raw = (FIXTURES / "sanitized_instruments.csv").read_text(encoding="utf-8")

    class _Resp:
        headers = {"Content-Type": "text/csv"}

        def read(self) -> bytes:
            return raw.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    t = UrllibKiteTransport()
    payload = t.request(
        method="GET",
        url="https://api.kite.trade/instruments",
        headers={"X-Kite-Version": "3"},
    )
    assert payload["format"] == "csv"
    assert payload["data"][0]["tradingsymbol"] == "RELIANCE"


def test_build_real_path_wraps_readonly_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    from quantfund.brokers.zerodha.auth import ZerodhaCredentials
    from quantfund.data.zerodha_hist.readonly_transport import ReadOnlyHistoricalTransport

    # Avoid network: force failure after transport construction by patching mark_connected
    env = {
        "QUANTFUND_ALLOW_ZERODHA_HISTORICAL": "1",
        "ZERODHA_API_KEY": "k",
        "ZERODHA_API_SECRET": "s",
        "ZERODHA_ACCESS_TOKEN": "t",
    }

    def _boom(self):
        # Inspect transport type then raise
        assert isinstance(self.transport, ReadOnlyHistoricalTransport)
        raise RuntimeError("kite_auth_probe")

    monkeypatch.setattr(KiteClient, "mark_connected", _boom)
    with pytest.raises(ZerodhaHistoricalError, match="authentication_failure"):
        build_zerodha_historical_provider(env=env, force_mock=False)

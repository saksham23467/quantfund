"""End-to-end Phase 1: raw → dataset → backtest metadata (development_only)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from quantfund.analytics.report import build_report_dict, write_reports
from quantfund.backtest.engine import BacktestConfig, BacktestEngine
from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.datasets.builder import DatasetBuilder
from quantfund.data.datasets.config_from_manifest import backtest_config_from_manifest
from quantfund.data.datasets.manifest import ResearchEligibility, SourceGrade
from quantfund.data.datasets.reader import DatasetReader
from quantfund.data.ingest.pipeline import ingest_bars_raw
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.providers.base import DataProvider
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseVersion,
)
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


class _YFinancelikeProvider(DataProvider):
    """Static provider named yfinance for development labeling tests (no network)."""

    def __init__(self, bars: list[MarketBar]) -> None:
        self._bars = bars

    @property
    def name(self) -> str:
        return "yfinance"

    def get_instruments(self):
        return [Instrument(symbol="TEST", provider_symbol="TEST.NS")]

    def get_history(self, symbol, start=None, end=None):
        return list(self._bars)


def _bars() -> list[MarketBar]:
    return [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=100,
            high=105,
            low=99,
            close=102,
            volume=1000,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 3),
            symbol="TEST",
            open=102,
            high=108,
            low=101,
            close=107,
            volume=1100,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 4),
            symbol="TEST",
            open=107,
            high=110,
            low=106,
            close=109,
            volume=1200,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 5),
            symbol="TEST",
            open=109,
            high=112,
            low=108,
            close=111,
            volume=1300,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 8),
            symbol="TEST",
            open=111,
            high=115,
            low=110,
            close=114,
            volume=1400,
        ),
    ]


def test_phase1_end_to_end_development_dataset(tmp_path: Path):
    bars = _bars()
    provider = _YFinancelikeProvider(bars)
    raw = ingest_bars_raw(
        provider=provider,
        instruments=[Instrument(symbol="TEST", provider_symbol="TEST.NS")],
        raw_root=tmp_path / "raw",
        download_id="phase1_e2e",
    )

    universe = UniverseVersion(
        universe_id="nifty50",
        universe_version="stage_a_sample_v1",
        completeness=UniverseCompleteness.CURRENT_SNAPSHOT_ONLY,
        as_of_date=date(2024, 1, 8),
        source="manual_sample",
        members=[UniverseMember(instrument_id="NSE:TEST", symbol="TEST")],
    )
    calendar = FakeCalendarProvider(
        [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5), date(2024, 1, 8)]
    )

    builder = DatasetBuilder(tmp_path / "datasets")
    manifest, quality = builder.build(
        dataset_id="india_eq_nifty50_daily_dev",
        dataset_version="2024.01.08+test",
        bars=bars,
        universe=universe,
        calendar=calendar,
        source="yfinance",
        download_id=raw.download_id,
        download_timestamp=raw.downloaded_at,
        raw_root=raw.root,
        source_grade=SourceGrade.NON_EXCHANGE,
        actions=[
            CorporateAction(
                action_id="div1",
                instrument_id="NSE:TEST",
                symbol="TEST",
                action_type=CorporateActionType.DIVIDEND,
                ex_date=date(2024, 1, 5),
                cash_amount=1.5,
                source="test",
                verified=True,
            )
        ],
    )

    assert manifest.research_eligibility == ResearchEligibility.DEVELOPMENT_ONLY
    assert manifest.universe_completeness == UniverseCompleteness.CURRENT_SNAPSHOT_ONLY
    assert quality.error_count == 0
    assert (tmp_path / "datasets" / manifest.dataset_id / manifest.dataset_version / "manifest.json").exists()

    reader = DatasetReader.open(
        tmp_path / "datasets", manifest.dataset_id, manifest.dataset_version
    )
    # Execution uses RAW prices
    exec_bars = reader.get_history("TEST", price_field="raw")
    assert exec_bars[0].close == 102

    cfg = backtest_config_from_manifest(manifest, initial_capital=100_000.0)
    assert cfg.dataset_id == manifest.dataset_id
    assert cfg.research_eligibility == "development_only"
    assert cfg.dataset_warnings

    engine = BacktestEngine(BuyAndHoldStrategy(symbol="TEST", allocation=0.95), config=cfg)
    result = engine.run(exec_bars)

    assert result.dataset_id == manifest.dataset_id
    assert result.dataset_version == manifest.dataset_version
    assert result.research_eligibility == "development_only"
    assert len(result.portfolio.fills) == 1
    # next-bar open execution unchanged
    assert result.portfolio.fills[0].timestamp == exec_bars[1].timestamp

    report = build_report_dict(result)
    assert report["dataset_id"] == manifest.dataset_id
    assert report["research_eligibility"] == "development_only"
    assert report["dataset_warnings"]

    out = tmp_path / "experiments"
    json_path, text_path = write_reports(result, out)
    text = text_path.read_text(encoding="utf-8")
    assert "DATASET WARNINGS" in text
    assert "development_only" in text


def test_same_bar_execution_still_forbidden():
    with pytest.raises(ValueError, match="same-bar"):
        BacktestEngine(
            BuyAndHoldStrategy(symbol="TEST"),
            config=BacktestConfig(allow_same_bar_execution=True),
        )

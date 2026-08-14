"""Dataset manifest, hashing, eligibility, reader as-of, immutability."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.corporate_actions.policies import default_split_bonus_policy
from quantfund.data.datasets.builder import DatasetBuilder
from quantfund.data.datasets.manifest import (
    DatasetKind,
    ResearchEligibility,
    SourceGrade,
)
from quantfund.data.datasets.reader import DatasetReader
from quantfund.data.ingest.checksums import verify_checksums
from quantfund.data.ingest.pipeline import ingest_bars_raw
from quantfund.data.models import Instrument, MarketBar
from quantfund.data.providers.base import DataProvider
from quantfund.data.universe.models import (
    UniverseCompleteness,
    UniverseMember,
    UniverseVersion,
)


class _StaticProvider(DataProvider):
    def __init__(self, bars: list[MarketBar]) -> None:
        self._bars = bars

    @property
    def name(self) -> str:
        return "yfinance"

    def get_instruments(self):
        return [Instrument(symbol="TEST", provider_symbol="TEST.NS")]

    def get_history(self, symbol, start=None, end=None):
        return [b for b in self._bars if b.symbol == symbol]


def _bars() -> list[MarketBar]:
    return [
        MarketBar(
            timestamp=datetime(2024, 1, 2),
            symbol="TEST",
            open=200,
            high=210,
            low=190,
            close=200,
            volume=100,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 3),
            symbol="TEST",
            open=100,
            high=105,
            low=95,
            close=100,
            volume=200,
        ),
        MarketBar(
            timestamp=datetime(2024, 1, 4),
            symbol="TEST",
            open=101,
            high=106,
            low=100,
            close=105,
            volume=200,
        ),
    ]


def _universe() -> UniverseVersion:
    return UniverseVersion(
        universe_id="nifty50",
        universe_version="stage_a_test",
        completeness=UniverseCompleteness.CURRENT_SNAPSHOT_ONLY,
        as_of_date=date(2024, 1, 8),
        source="test",
        members=[UniverseMember(instrument_id="NSE:TEST", symbol="TEST")],
    )


def _calendar() -> FakeCalendarProvider:
    return FakeCalendarProvider(
        [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    )


def test_duplicate_bars_fail_quality(tmp_path: Path):
    bars = _bars() + [
        MarketBar(
            timestamp=datetime(2024, 1, 3),
            symbol="TEST",
            open=100,
            high=105,
            low=95,
            close=100,
            volume=1,
        )
    ]
    builder = DatasetBuilder(tmp_path / "datasets")
    with pytest.raises(ValueError, match="ERROR"):
        builder.build(
            dataset_id="dup",
            dataset_version="v1",
            bars=bars,
            universe=_universe(),
            calendar=_calendar(),
            source="yfinance",
            download_id="d1",
            source_grade=SourceGrade.NON_EXCHANGE,
        )


def test_yfinance_dataset_is_development_only(tmp_path: Path):
    builder = DatasetBuilder(tmp_path / "datasets")
    manifest, quality = builder.build(
        dataset_id="dev_ds",
        dataset_version="v1",
        bars=_bars(),
        universe=_universe(),
        calendar=_calendar(),
        source="yfinance",
        download_id="d1",
        source_grade=SourceGrade.NON_EXCHANGE,
        actions=[
            CorporateAction(
                action_id="s1",
                instrument_id="NSE:TEST",
                symbol="TEST",
                action_type=CorporateActionType.SPLIT,
                ex_date=date(2024, 1, 3),
                ratio_num=2,
                ratio_den=1,
                source="test",
                verified=True,
            )
        ],
    )
    assert manifest.research_eligibility == ResearchEligibility.DEVELOPMENT_ONLY
    assert manifest.source_grade == SourceGrade.NON_EXCHANGE
    assert manifest.dataset_status == "development"
    assert manifest.calendar_verified is False
    assert manifest.adjustment_policy["policy_id"] == "split_bonus_v1"
    assert any("DEVELOPMENT DATASET" in w for w in manifest.warnings)
    assert any("NOT POINT-IN-TIME" in w for w in manifest.warnings)
    assert any("Calendar is not verified" in w for w in manifest.warnings)
    assert quality.calendar_verified is False
    assert any(i.code == "calendar_unverified" for i in quality.issues)


def test_unverified_calendar_forces_development_only_even_with_other_ok_fields():
    """Proxy/unverified calendar alone is enough to gate eligibility."""
    from datetime import timezone

    from quantfund.data.datasets.manifest import DatasetManifest

    manifest = DatasetManifest(
        dataset_id="gate",
        dataset_version="v1",
        dataset_kind=DatasetKind.RESEARCH,
        research_eligibility=ResearchEligibility.RESEARCH_READY,
        source="paid_vendor",
        source_grade=SourceGrade.PAID,
        dataset_status="research",
        download_id="d1",
        download_timestamp=datetime.now(timezone.utc),
        date_range_start="2024-01-02",
        date_range_end="2024-01-04",
        universe_id="nifty50",
        universe_version="full_pit_v1",
        universe_completeness=UniverseCompleteness.FULL_PIT,
        calendar_id="XBOM_PROXY_UNVERIFIED",
        calendar_version="x",
        calendar_verified=False,
        adjustment_policy={"policy_id": "split_bonus_v1"},
        content_hash="sha256:abc",
        bar_count=3,
        instrument_count=1,
    )
    assert manifest.research_eligibility == ResearchEligibility.DEVELOPMENT_ONLY
    assert any("Calendar is not verified" in w for w in manifest.warnings)


def test_manifest_records_adjustment_policy(tmp_path: Path):
    policy = default_split_bonus_policy()
    builder = DatasetBuilder(tmp_path / "datasets")
    manifest, _ = builder.build(
        dataset_id="pol",
        dataset_version="v1",
        bars=_bars(),
        universe=_universe(),
        calendar=_calendar(),
        policy=policy,
        source="yfinance",
        download_id="d1",
    )
    assert manifest.adjustment_policy == policy.to_manifest_dict()


def test_dataset_hashes_reproducible(tmp_path: Path):
    builder = DatasetBuilder(tmp_path / "datasets")
    kwargs = dict(
        bars=_bars(),
        universe=_universe(),
        calendar=_calendar(),
        source="yfinance",
        download_id="d1",
    )
    m1, _ = builder.build(dataset_id="h1", dataset_version="v1", **kwargs)
    m2, _ = builder.build(dataset_id="h2", dataset_version="v1", **kwargs)
    assert m1.content_hash == m2.content_hash


def test_new_transformation_requires_new_version(tmp_path: Path):
    builder = DatasetBuilder(tmp_path / "datasets")
    builder.build(
        dataset_id="t",
        dataset_version="v1",
        bars=_bars(),
        universe=_universe(),
        calendar=_calendar(),
        source="yfinance",
        download_id="d1",
    )
    with pytest.raises(FileExistsError):
        builder.build(
            dataset_id="t",
            dataset_version="v1",
            bars=_bars(),
            universe=_universe(),
            calendar=_calendar(),
            source="yfinance",
            download_id="d1",
        )
    # New version OK
    m2, _ = builder.build(
        dataset_id="t",
        dataset_version="v2",
        bars=_bars(),
        universe=_universe(),
        calendar=_calendar(),
        source="yfinance",
        download_id="d1",
        actions=[
            CorporateAction(
                action_id="s1",
                instrument_id="NSE:TEST",
                symbol="TEST",
                action_type=CorporateActionType.SPLIT,
                ex_date=date(2024, 1, 3),
                ratio_num=2,
                ratio_den=1,
                source="test",
                verified=True,
            )
        ],
    )
    assert m2.dataset_version == "v2"


def test_as_of_reader_hides_future_bars(tmp_path: Path):
    builder = DatasetBuilder(tmp_path / "datasets")
    builder.build(
        dataset_id="asof",
        dataset_version="v1",
        bars=_bars(),
        universe=_universe(),
        calendar=_calendar(),
        source="yfinance",
        download_id="d1",
    )
    reader = DatasetReader.open(tmp_path / "datasets", "asof", "v1")
    bars = reader.get_history("TEST", as_of=datetime(2024, 1, 3))
    assert [b.timestamp.date() for b in bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert all(b.timestamp <= datetime(2024, 1, 3) for b in bars)


def test_raw_immutable_after_ingest(tmp_path: Path):
    provider = _StaticProvider(_bars())
    result = ingest_bars_raw(
        provider=provider,
        instruments=[Instrument(symbol="TEST", provider_symbol="TEST.NS")],
        raw_root=tmp_path / "raw",
        download_id="imm1",
    )
    assert verify_checksums(result.root)
    # Mutating a raw file breaks verification
    target = next((result.root / "bars").glob("*.csv"))
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    assert verify_checksums(result.root) is False
    # Cannot overwrite same download_id
    with pytest.raises(FileExistsError):
        ingest_bars_raw(
            provider=provider,
            instruments=[Instrument(symbol="TEST")],
            raw_root=tmp_path / "raw",
            download_id="imm1",
        )


def test_raw_ohlc_unchanged_in_dataset_parquet(tmp_path: Path):
    bars = _bars()
    builder = DatasetBuilder(tmp_path / "datasets")
    builder.build(
        dataset_id="rawchk",
        dataset_version="v1",
        bars=bars,
        universe=_universe(),
        calendar=_calendar(),
        source="yfinance",
        download_id="d1",
        actions=[
            CorporateAction(
                action_id="s1",
                instrument_id="NSE:TEST",
                symbol="TEST",
                action_type=CorporateActionType.SPLIT,
                ex_date=date(2024, 1, 3),
                ratio_num=2,
                ratio_den=1,
                source="test",
                verified=True,
            )
        ],
    )
    reader = DatasetReader.open(tmp_path / "datasets", "rawchk", "v1")
    raw = reader.get_history("TEST", price_field="raw")
    assert raw[0].close == 200
    adj = reader.get_history("TEST", price_field="adjusted")
    assert adj[0].close == 100

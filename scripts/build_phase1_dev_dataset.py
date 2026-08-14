#!/usr/bin/env python3
"""Build a Phase 1 DEVELOPMENT dataset from the synthetic fixture (no network).

Output is explicitly research_eligibility=development_only.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from quantfund.config import PATHS
from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.corporate_actions.models import CorporateAction, CorporateActionType
from quantfund.data.datasets.builder import DatasetBuilder
from quantfund.data.datasets.manifest import SourceGrade
from quantfund.data.ingest.pipeline import ingest_bars_raw
from quantfund.data.models import Instrument
from quantfund.data.normalize import dataframe_to_bars
from quantfund.data.providers.base import DataProvider
from quantfund.data.universe.membership import UniverseMembershipStore
from quantfund.data.validate import validate_bars


class FixtureProvider(DataProvider):
    def __init__(self, bars) -> None:
        self._bars = bars

    @property
    def name(self) -> str:
        return "yfinance"

    def get_instruments(self):
        return [Instrument(symbol="TEST", provider_symbol="TEST.NS")]

    def get_history(self, symbol, start=None, end=None):
        return list(self._bars)


def main() -> int:
    fixture = ROOT / "tests" / "fixtures" / "synthetic_bars.csv"
    df = pd.read_csv(fixture, parse_dates=["timestamp"])
    bars = validate_bars(dataframe_to_bars(df, symbol="TEST"))

    provider = FixtureProvider(bars)
    raw = ingest_bars_raw(
        provider=provider,
        instruments=[Instrument(symbol="TEST", provider_symbol="TEST.NS")],
        raw_root=PATHS.raw_dir,
        extra_meta={"label": "SYNTHETIC_FIXTURE_VIA_YFINANCE_PROVIDER_NAME", "note": "dev only"},
    )

    store = UniverseMembershipStore(PATHS.universes_dir)
    universe = store.load("nifty50", "stage_a_sample_v1")

    open_days = sorted({b.timestamp.date() for b in bars})
    calendar = FakeCalendarProvider(
        open_days,
        calendar_id="SYNTHETIC_SESSIONS",
        calendar_version="synthetic_fixture_v1",
    )

    builder = DatasetBuilder(PATHS.datasets_dir)
    version = datetime.now(timezone.utc).strftime("%Y.%m.%d+") + raw.download_id[-8:]
    manifest, quality = builder.build(
        dataset_id="india_eq_nifty50_daily_dev",
        dataset_version=version,
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
                action_id="synthetic_div",
                instrument_id="NSE:TEST",
                symbol="TEST",
                action_type=CorporateActionType.DIVIDEND,
                ex_date=date(2024, 1, 5),
                cash_amount=1.0,
                source="synthetic",
                verified=False,
                notes="Synthetic dividend for pipeline demo only",
            )
        ],
    )

    print("Built DEVELOPMENT dataset")
    print(f"  dataset_id={manifest.dataset_id}")
    print(f"  dataset_version={manifest.dataset_version}")
    print(f"  research_eligibility={manifest.research_eligibility.value}")
    print(f"  universe_completeness={manifest.universe_completeness.value}")
    print(f"  source_grade={manifest.source_grade.value}")
    print(f"  content_hash={manifest.content_hash}")
    print("  warnings:")
    for w in manifest.warnings:
        print(f"    - {w}")
    print(f"  quality errors={quality.error_count} warnings={quality.warning_count}")
    print(f"  path={PATHS.datasets_dir / manifest.dataset_id / manifest.dataset_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

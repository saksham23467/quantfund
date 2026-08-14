#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.models import PaperSessionConfig, SessionMode
from quantfund.phase14.market_data import YFinanceSimulationMarketDataProvider
from quantfund.phase14.shadow import ShadowEngine
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


def main() -> int:
    prov = YFinanceSimulationMarketDataProvider.from_fixture_bars(n=10)
    cal = FakeCalendarProvider(
        open_sessions=sorted({b.timestamp.date() for b in prov._stream}), verified=True
    )
    cfg = PaperSessionConfig(
        session_id="phase14_shadow",
        mode=SessionMode.INFRASTRUCTURE_SANDBOX,
        certified_eligibility="development_only",
        strategy_id="buy_and_hold",
        strategy_version="1.0.0",
        cost_model_id="equity_delivery_v1",
        slippage_model_id="fixed_bps_5",
    )
    eng = ShadowEngine(
        provider=prov,
        strategy_factory=lambda: BuyAndHoldStrategy(symbol="RELIANCE", allocation=0.5),
        session_config=cfg,
        calendar=cal,
        instruments=[Instrument(symbol="RELIANCE", exchange="NSE", instrument_id="NSE:RELIANCE")],
        max_staleness_seconds=None,
    )
    eng.start(["RELIANCE"])
    eng.drain()
    eng.stop()
    print("PHASE 14 SHADOW")
    print(eng.result.to_dict())
    return 0 if eng.result.would_orders else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 15 preflight — no orders."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.calendar.fake import FakeCalendarProvider
from quantfund.data.models import Instrument
from quantfund.paper.models import PaperSessionConfig, SessionMode
from quantfund.phase14.market_data import YFinanceSimulationMarketDataProvider
from quantfund.phase15.broker_readonly import SimulatedReadOnlyBroker
from quantfund.phase15.providers import CapableMarketDataProvider, ProviderProvenance, YFINANCE_CAPS
from quantfund.phase15.shadow_session import Phase15ShadowSession
from quantfund.strategies.examples.buy_and_hold import BuyAndHoldStrategy


def main() -> int:
    symbol = "RELIANCE"
    factory = lambda: BuyAndHoldStrategy(symbol=symbol)
    meta = factory().metadata()
    base = YFinanceSimulationMarketDataProvider.from_fixture_bars(symbol=symbol, n=3)
    provider = CapableMarketDataProvider(
        base,
        capabilities=YFINANCE_CAPS,
        provenance=ProviderProvenance(
            provider_id=YFINANCE_CAPS.provider_id,
            source_grade=YFINANCE_CAPS.source_grade,
            simulation_only=True,
            research_eligible=False,
            license_status=YFINANCE_CAPS.license_status,
            configured=False,
            mode="SIMULATED",
        ),
    )
    dates = sorted({b.timestamp.date() for b in base._stream})
    session = Phase15ShadowSession(
        provider=provider,
        strategy_factory=factory,
        session_config=PaperSessionConfig(
            session_id="phase15_preflight",
            mode=SessionMode.INFRASTRUCTURE_SANDBOX,
            strategy_id=meta.strategy_id,
            strategy_version=meta.strategy_version,
            certified_eligibility="development_only",
        ),
        calendar=FakeCalendarProvider(open_sessions=dates, verified=True),
        broker=SimulatedReadOnlyBroker(),
        instruments=[
            Instrument(
                symbol=symbol,
                exchange="NSE",
                isin="INE002A01018",
                instrument_id=f"NSE:{symbol}",
            )
        ],
    )
    pf = session.preflight()
    print("PHASE 15 PREFLIGHT")
    print(f"ok={pf['ok']}")
    print(f"live_trading={pf['live_trading']}")
    print(f"broker_can_place_orders={pf['broker_can_place_orders']}")
    print(f"market_data_mode={pf['market_data_mode']}")
    print(f"research_eligibility={pf['research_eligibility']}")
    return 0 if pf["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

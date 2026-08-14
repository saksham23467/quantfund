#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.phase11.connectivity_status import BrokerConnectivityStatus
from quantfund.phase11.paper_gates import Phase11PaperGateDecision
from quantfund.phase11.reports import build_paper_session_report, write_paper_session_report
from quantfund.phase11.trading_session import PaperTradingSession, PaperTradingState


def main() -> int:
    out = ROOT / "experiments" / "phase11_demo_report"
    sess = PaperTradingSession.create(
        session_id="phase11_report",
        connectivity=BrokerConnectivityStatus.SIMULATED,
        strategy_enabled=False,
    )
    # Non-eligible session report still documents DISABLED live
    sess.gate_decision = Phase11PaperGateDecision(
        paper_eligible=False,
        research_eligibility="development_only",
        connectivity=BrokerConnectivityStatus.SIMULATED,
        blockers=["development_only_dataset_cannot_be_paper_eligible"],
    )
    sess.state = PaperTradingState.FAILED
    sess.fail_reason = "paper_not_eligible"
    report = build_paper_session_report(
        sess,
        strategy_id="none",
        dataset="DEVELOPMENT_ONLY",
        configuration_hash="sha256:phase11",
        data_quality_warnings=["no_licensed_package"],
    )
    jp, tp = write_paper_session_report(report, out_dir=out)
    print(report.to_text())
    print(f"Wrote {jp}")
    print(f"Wrote {tp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Standalone smoke test for the gateway (run with the repo venv)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from quantfund_terminal.backend.app.main import app  # noqa: E402

client = TestClient(app)


def _check(method: str, path: str, **kw) -> dict:
    resp = client.request(method, path, **kw)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text[:200]}"
    return resp.json()


def main() -> int:
    health = _check("GET", "/health")
    assert health["safety_state"]["live_trading"] == "DISABLED"
    assert health["safety_state"]["broker_write_capability"] == "DISABLED"

    cert = _check("GET", "/api/certification")
    assert cert["verdict"] in {"DEVELOPMENT_ONLY", "RESEARCH_ELIGIBLE"}
    assert cert["research_eligible"] is False  # current honest state

    lb = _check("GET", "/api/leaderboard")
    assert lb["accepted_count"] == 0
    assert len(lb["rows"]) >= 1

    audit = _check("GET", "/api/audit")
    assert audit["research_integrity"]["gates_modified"] is False

    market = _check("GET", "/api/market")
    assert market["data_class"] == "DEMO_SYNTHETIC"
    assert "NIFTY50_PROXY" in market["indices"]

    strat = _check("POST", "/api/strategies", json={"name": "demo_mom", "family": "momentum"})
    assert strat["status"] == "DRAFT"

    bt = _check(
        "POST",
        "/api/backtest",
        json={"family": "momentum", "cost_bps": 10, "slippage_bps": 5},
    )
    assert "summary" in bt and "sharpe" in bt["summary"]
    assert bt["certification"]["research_eligible"] is False

    factors = _check("GET", "/api/factors?lookback=126")
    assert len(factors["factors"]) == 5

    port = _check(
        "POST",
        "/api/portfolio",
        json={"holdings": [
            {"symbol": "RELIANCE", "weight": 0.5},
            {"symbol": "TCS", "weight": 0.3},
            {"symbol": "HDFCBANK", "weight": 0.2},
        ]},
    )
    assert "beta_vs_market_proxy" in port

    risk = _check(
        "POST",
        "/api/risk",
        json={"holdings": [
            {"symbol": "RELIANCE", "weight": 0.6},
            {"symbol": "SBIN", "weight": 0.4},
        ]},
    )
    assert "stress_tests" in risk

    cop = _check("POST", "/api/copilot", json={"prompt": "Find momentum stocks"})
    assert cop["intent"] == "find_momentum_stocks"
    cop2 = _check("POST", "/api/copilot", json={"prompt": "Build a low-vol strategy"})
    assert cop2["intent"] == "build_low_vol_strategy"
    cop3 = _check("POST", "/api/copilot", json={"prompt": "Explain why Sharpe fell"})
    assert cop3["intent"] == "explain_sharpe_drop"

    print("SMOKE_OK: all endpoints healthy; safety DISABLED; verdict DEVELOPMENT_ONLY")
    print("  certification.verdict     =", cert["verdict"])
    print("  leaderboard.accepted      =", lb["accepted_count"])
    print("  backtest.sharpe (demo)    =", bt["summary"]["sharpe"], "(illustrative)")
    print("  market.NIFTY50_PROXY      =", market["indices"]["NIFTY50_PROXY"]["level"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

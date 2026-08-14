"""Smoke test for the v2 multi-tenant SaaS surface (run with the repo venv)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from quantfund_terminal.backend.app.main import app  # noqa: E402

client = TestClient(app)
ADMIN = {"X-Org-Slug": "demo-capital", "X-User-Email": "admin@demo-capital.in", "X-Role": "admin"}
VIEWER = {"X-Org-Slug": "demo-capital", "X-User-Email": "v@demo-capital.in", "X-Role": "viewer"}


def _get(path, headers=None, code=200):
    r = client.get(path, headers=headers)
    assert r.status_code == code, f"GET {path} -> {r.status_code}: {r.text[:200]}"
    return r.json()


def _post(path, body=None, headers=None, code=200):
    r = client.post(path, json=body or {}, headers=headers)
    assert r.status_code == code, f"POST {path} -> {r.status_code}: {r.text[:200]}"
    return r.json()


def main() -> int:
    # identity + RBAC
    me = _get("/api/v2/me", ADMIN)
    assert me["role"] == "admin" and me["permissions"]["admin"] is True
    _get("/api/v2/orgs", VIEWER, code=403)          # viewer blocked
    orgs = _get("/api/v2/orgs", ADMIN)
    assert len(orgs["orgs"]) >= 3

    # dataset exchange — authoritative, fail-closed
    ds = _get("/api/v2/datasets")
    assert ds["research_eligible_count"] == 0
    assert any(d["dataset_id"] == "zerodha_nse_daily" for d in ds["datasets"])
    z = _get("/api/v2/datasets/zerodha_nse_daily")
    assert z["certification"]["verdict"] == "DEVELOPMENT_ONLY"

    # marketplace + reproducibility proof
    mkt = _get("/api/v2/marketplace")
    assert mkt["authoritative_gated"]["accepted_count"] == 0
    demo_rows = mkt["demo_leaderboard"]["rows"]
    assert len(demo_rows) >= 5 and all(r["status"] == "RESEARCH_ONLY" for r in demo_rows)
    bt_id = demo_rows[0]["backtest_id"]
    proof = _get(f"/api/v2/marketplace/{bt_id}/proof")
    assert proof["reproducible"] is True, proof

    # publish requires pm+ ; viewer blocked, admin ok
    _post("/api/v2/marketplace/publish", {"name": "x", "family": "momentum"}, VIEWER, code=403)
    pub = _post(
        "/api/v2/marketplace/publish",
        {"name": "Copilot Momentum", "family": "momentum", "params": {"lookback": 126}},
        ADMIN,
    )
    assert pub["status"] == "RESEARCH_ONLY" and pub["proof"]["experiment_hash"]

    # studio: attribution / risk decomposition / scenario
    holdings = {"holdings": [
        {"symbol": "RELIANCE", "weight": 0.3}, {"symbol": "TCS", "weight": 0.3},
        {"symbol": "HDFCBANK", "weight": 0.2}, {"symbol": "SBIN", "weight": 0.2}]}
    attr = _post("/api/v2/studio/attribution", holdings)
    assert "contributions" in attr and len(attr["contributions"]) == 5
    rd = _post("/api/v2/studio/risk-decomposition", holdings)
    assert rd["contributions"] and rd["portfolio_volatility_annualized"] > 0
    sc = _post("/api/v2/studio/scenario", holdings)
    assert any(s["scenario"] == "gfc_2008_like" for s in sc["scenarios"])

    # copilot v2 (audit-logged, record hash)
    cop = _post("/api/v2/copilot", {"prompt": "Find momentum stocks"}, ADMIN)
    assert cop["intent"] == "find_momentum_stocks" and cop["record_hash"].startswith("sha256:")

    # investor dashboard
    inv = _get("/api/v2/investor")
    assert inv["saas_metrics"]["arr_inr"] > 0
    assert len(inv["competitive_comparison"]) == 5
    assert inv["dataset_moat"]["research_eligible"] == 0

    # billing
    plans = _get("/api/v2/billing/plans")
    assert "team" in plans["plans"]
    ck = _post("/api/v2/billing/checkout", {"plan": "team"}, ADMIN)
    assert ck["provider"] == "mock" and ck["plan"] == "team"
    _post("/api/v2/billing/checkout", {"plan": "team"}, VIEWER, code=403)

    # audit: immutable records + hash-chain verification
    recs = _get("/api/v2/audit/records", ADMIN)
    assert recs["records"]
    verify = _get("/api/v2/audit/verify")
    assert verify["intact"] is True, verify
    log = _get("/api/v2/audit/log", ADMIN)
    assert any(e["action"] == "PUBLISH_MARKETPLACE" for e in log["entries"])

    # safety still disabled (unchanged core)
    health = _get("/health")
    assert health["safety_state"]["live_trading"] == "DISABLED"

    print("SMOKE_V2_OK")
    print("  orgs:", len(orgs["orgs"]), "| datasets eligible:", ds["research_eligible_count"])
    print("  marketplace demo rows:", len(demo_rows), "| proof reproducible:", proof["reproducible"])
    print("  ARR (INR):", inv["saas_metrics"]["arr_inr"], "| chain intact:", verify["intact"])
    print("  cache backend:", health.get("cache_backend"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

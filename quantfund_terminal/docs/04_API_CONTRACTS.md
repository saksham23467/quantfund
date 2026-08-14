# API Contracts (research_api gateway)

Base URL: `http://localhost:8000` (dev). All responses are JSON. The gateway is
**read-only** with respect to trading: it exposes no order/broker endpoints.
Interactive OpenAPI docs are served at `/docs` (FastAPI).

Every analytical response includes a `data_class` and, where relevant, a
`verdict` / `disclaimer` so the UI can badge provenance.

---

## System

### `GET /health`
```json
{ "status": "ok", "safety_state": { "live_trading": "DISABLED", "broker_write_capability": "DISABLED", "kill_switch": "ARMED", "...": "..." } }
```

### `GET /api/safety`
Returns the immutable safety posture:
```json
{ "live_trading": "DISABLED", "paper_trading": "NOT_STARTED", "broker_write_capability": "DISABLED",
  "kill_switch": "ARMED", "orders_submitted": 0, "place_order_called": 0,
  "auto_graduate_to_live": false, "product_mode": "READ_ONLY_RESEARCH_TERMINAL" }
```

---

## Feature 1 — Market Dashboard

### `GET /api/market`
```json
{
  "data_class": "DEMO_SYNTHETIC", "source": "synthetic_gbm_seed42", "mode": "delayed_fallback",
  "as_of": "2026-06-30",
  "indices": {
    "NIFTY50_PROXY":  { "level": 334.6, "change_pct_1d": 0.42, "annualized_vol_20d": 12.1 },
    "BANKNIFTY_PROXY":{ "level": 210.4, "change_pct_1d": -0.10, "annualized_vol_20d": 15.3 }
  },
  "sector_performance": { "IT": 0.51, "Financials": -0.12, "...": 0.0 },
  "top_gainers": [ { "symbol": "TCS", "change_pct": 1.83 } ],
  "top_losers":  [ { "symbol": "SBIN", "change_pct": -1.42 } ],
  "breadth": { "advancers": 12, "decliners": 8, "advance_decline_ratio": 1.5 },
  "volatility": { "nifty_proxy_annualized_20d": 12.1 },
  "disclaimer": "Synthetic demo data ..."
}
```
> Contract is stable when a licensed/exchange real-time feed replaces the demo
> panel; only `mode`/`data_class`/`source` change.

---

## Feature 2 — Research Lab

### `GET /api/strategies`
```json
{ "families": ["breakout","mean_reversion","momentum","trend","volatility"],
  "strategies": [ { "id": 1, "name": "my_mom", "family": "momentum", "params": {"lookback":126}, "status": "DRAFT", "note": "..." } ] }
```

### `POST /api/strategies`
Request:
```json
{ "name": "my_mom", "family": "momentum", "params": { "lookback": 126, "holding_top_n": 5 } }
```
Response: the created draft (`status: "DRAFT"`). Drafts are never auto-run and
never accepted without a research-eligible dataset.

---

## Feature 3 — Backtest Engine

### `POST /api/backtest`
Request:
```json
{ "family": "momentum", "universe": "DEMO_NIFTY20", "start": "2016-01-01", "end": "2026-06-30",
  "lookback": 126, "holding_top_n": 5, "rebalance_days": 21, "cost_bps": 10, "slippage_bps": 5 }
```
Response:
```json
{
  "summary": { "cagr": 0.08, "sharpe": 0.42, "sortino": 0.55, "max_drawdown": -0.31,
               "volatility": 0.19, "win_rate": 0.52, "profit_factor": 1.18,
               "turnover": 0.21, "exposure": 1.0, "n_periods": 2600 },
  "equity_curve":   [ { "date": "2016-07-05", "equity": 1.0 } ],
  "drawdown_curve": [ { "date": "2016-07-05", "drawdown": 0.0 } ],
  "config": { "...": "..." }, "data_class": "DEMO_SYNTHETIC", "n_symbols": 20, "warnings": [],
  "certification": { "verdict": "DEVELOPMENT_ONLY", "research_eligible": false,
                     "banner": "RESULTS ARE ILLUSTRATIVE — dataset is DEVELOPMENT_ONLY ..." }
}
```
Execution is next-bar (no look-ahead); costs+slippage charged on traded notional.

---

## Feature 4 — Factor Research

### `GET /api/factors?lookback=126`
```json
{
  "factors": [
    { "factor": "momentum", "is_proxy": false, "annualized_return": 0.05, "sharpe": 0.31,
      "cumulative": [ { "date": "2016-07-05", "value": 1.0 } ] },
    { "factor": "value", "is_proxy": true, "...": "..." }
  ],
  "correlations": { "momentum": { "momentum": 1.0, "low_vol": -0.2 } },
  "data_class": "DEMO_SYNTHETIC",
  "disclaimer": "value/quality are labelled proxies ..."
}
```

---

## Feature 5 — Portfolio Analytics

### `POST /api/portfolio`
Request:
```json
{ "holdings": [ { "symbol": "RELIANCE", "weight": 0.5 },
                { "symbol": "TCS", "quantity": 100, "price": 3800 } ] }
```
Response:
```json
{ "weights": { "RELIANCE": 0.5 }, "beta_vs_market_proxy": 0.98,
  "var_95_daily": -0.021, "var_99_daily": -0.034, "max_drawdown": -0.28,
  "sector_exposure": { "Energy": 0.5, "IT": 0.5 }, "concentration_hhi": 0.5,
  "top_holdings": [ { "symbol": "RELIANCE", "weight": 0.5 } ],
  "correlation": { "RELIANCE": { "TCS": 0.4 } }, "data_class": "DEMO_SYNTHETIC", "note": "..." }
```

---

## Feature 6 — Risk Command Center

### `POST /api/risk`
Request: same `holdings` shape as portfolio.
Response:
```json
{ "gross_exposure": 1.0, "net_exposure": 1.0, "long_exposure": 1.0, "short_exposure": 0.0,
  "leverage": 1.0, "beta": 0.98, "annualized_volatility": 0.18, "var_95_daily": -0.02,
  "largest_position": { "symbol": "RELIANCE", "weight": 0.6 },
  "sector_concentration": { "Energy": 0.6, "Financials": 0.4 },
  "stress_tests": { "market_down_5pct": { "market_shock": -0.05, "estimated_portfolio_pnl": -0.049 } },
  "data_class": "DEMO_SYNTHETIC", "note": "..." }
```

---

## Feature 7 — AI Research Copilot

### `POST /api/copilot`
Request: `{ "prompt": "Find momentum stocks" }`
Response:
```json
{ "intent": "find_momentum_stocks", "summary": "Rank the PIT universe by 6-month momentum ...",
  "generated_sql": "SELECT fs.symbol, fs.score ... WHERE d.certification = 'RESEARCH_ELIGIBLE' ...",
  "workflow_steps": [ "Resolve PIT universe membership ...", "..." ],
  "api_calls": [ "GET /api/factors?factor=momentum", "GET /api/certification" ],
  "disclaimer": "Plan only. ... No orders, no paper/live trading.",
  "safety_note": "read_only; broker_writes=DISABLED; kill_switch=ARMED",
  "confidence": 0.9, "matched": true }
```

---

## Feature 8 — Dataset Certification (moat)

### `GET /api/certification`
Backed by `reports/research_data_certification.json` (unmodified core verdict):
```json
{ "available": true, "verdict": "DEVELOPMENT_ONLY", "research_eligible": false,
  "source_grade": "non_exchange", "data_class": "DEVELOPMENT_DATA",
  "content_hash": "sha256:8b62...", "reproducible": true, "immutable": true, "leakage_safe": false,
  "dimensions": { "membership_coverage_ratio": 0.0, "instrument_identity_coverage": 0.0,
                  "delisted_coverage": "unknown", "corporate_action_coverage": "none",
                  "calendar_quality": { "calendar_verified": false, "calendar_errors": 0 } },
  "blockers": [ "source_grade=non_exchange ...", "..." ],
  "capability_gaps": [ "index_membership: no authoritative PIT membership ledger ..." ],
  "pit_universe": { "completeness": "none", "membership_coverage_ratio": 0.0 },
  "why_it_matters": "Most 'quant' platforms backtest on survivorship-biased ...",
  "safety_state": { "...": "..." }, "generated_at": "..." }
```

---

## Feature 9 — Strategy Marketplace / Leaderboard

### `GET /api/leaderboard`
Backed by `reports/phase19_strategy_search.json`:
```json
{ "ran_search": false, "stopped_reason": "research_eligibility_false",
  "families": ["trend_following","momentum","mean_reversion","breakout","volatility_regime"],
  "funnel": { "candidates_tested": 0, "final_accepted_candidates": 0 },
  "gate_policy": { "dsr_min": 0.95, "min_oos_sharpe": 0.5 },
  "accepted_count": 0, "accepted_ids": [], "auto_promotion": { "enabled": false },
  "prerequisite": { "blockers": [ "phase18_research_eligible=false ...", "..." ] },
  "rows": [ { "strategy": "Cross-Sectional Momentum", "family": "momentum",
             "cagr": null, "sharpe": null, "max_drawdown": null, "dsr": null,
             "status": "BLOCKED_PENDING_ELIGIBILITY" } ],
  "safety": { "...": "..." }, "statement": "Acceptance requires a research-eligible dataset ..." }
```

---

## Feature 10 — Institutional Audit Trail

### `GET /api/audit`
```json
{ "dataset_hash": "sha256:8b62...", "dataset_immutable": true,
  "reproducibility_status": "REPRODUCIBLE", "experiment_hash": null, "experiments_recorded": 0,
  "leakage_checks": { "leakage_safe": false, "pit_universe_enforced": true,
                      "next_bar_execution": true, "survivorship_protection": true },
  "research_integrity": { "verdict": "DEVELOPMENT_ONLY", "research_eligible": false,
                          "fail_closed": true, "gates_modified": false, "auto_promotion": false },
  "safety_state": { "...": "..." }, "statement": "Every result is bound to an immutable dataset hash ..." }
```

## Error model

Non-200 responses use FastAPI's default `{ "detail": "..." }`. The gateway
returns 4xx for bad input and 5xx for internal errors; it never returns an
"accepted" verdict for a non-eligible dataset.

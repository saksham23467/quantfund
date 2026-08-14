# Folder Structure

The product layer lives in `quantfund_terminal/` at the repo root (named to avoid
shadowing Python's stdlib `platform`). It depends on the existing, unmodified
`quantfund` package under `src/`.

```
quantfund_terminal/
├── README.md                     # run + demo instructions
├── docs/                         # the 9 deliverables (this folder)
│   ├── 01_ARCHITECTURE.md
│   ├── 02_FOLDER_STRUCTURE.md
│   ├── 03_DATABASE_SCHEMA.md
│   ├── 04_API_CONTRACTS.md
│   ├── 05_UI_WIREFRAMES.md
│   ├── 06_INVESTOR_DEMO_FLOW.md
│   ├── 07_DEVELOPMENT_ROADMAP.md
│   ├── 08_REVENUE_MODEL.md
│   └── 09_COMPETITIVE_COMPARISON.md
│
├── backend/                      # research_api gateway (FastAPI, read-only)
│   ├── requirements.txt
│   ├── run.sh                    # boots uvicorn on :8000 using repo .venv
│   ├── smoke_test.py             # end-to-end endpoint test vs real reports
│   └── app/
│       ├── __init__.py           # puts repo root on sys.path (imports quantfund)
│       ├── main.py               # FastAPI app, CORS, router wiring, /health /api/safety
│       ├── config.py             # paths + immutable SAFETY_STATE
│       ├── schemas.py            # Pydantic request models (API contracts)
│       ├── routers/
│       │   ├── market.py         # GET /api/market
│       │   ├── research.py       # GET/POST /api/strategies
│       │   ├── backtest.py       # POST /api/backtest
│       │   ├── factors.py        # GET /api/factors
│       │   ├── portfolio.py      # POST /api/portfolio
│       │   ├── risk.py           # POST /api/risk
│       │   ├── copilot.py        # POST /api/copilot
│       │   └── moat.py           # GET /api/certification | /api/leaderboard | /api/audit
│       └── services/
│           ├── panel.py               # cached synthetic demo panel
│           ├── market_service.py      # indices/sectors/breadth/movers/vol
│           ├── certification_service.py  # reads reports/research_data_certification.json
│           ├── leaderboard_service.py    # reads reports/phase19_strategy_search.json
│           ├── audit_service.py          # dataset/experiment hashes, leakage, integrity
│           └── strategy_store.py         # in-memory draft store (Postgres in prod)
│
├── analytics_engine/             # pure-python quant library (no I/O, no orders)
│   ├── __init__.py
│   ├── metrics.py                # CAGR/Sharpe/Sortino/MaxDD/Vol/Win/PF/Turnover/Exposure
│   ├── backtest.py               # vectorized, next-bar, cost+slippage aware
│   ├── factors.py                # momentum/quality/value/low_vol/size + corr + rolling sharpe
│   ├── portfolio.py              # beta/VaR/sector/drawdown/concentration/correlation
│   ├── risk.py                   # exposure/leverage/vol/VaR/stress tests
│   └── sample_data.py            # DETERMINISTIC synthetic panel (DEMO_SYNTHETIC)
│
├── copilot/                      # deterministic NL research copilot
│   ├── __init__.py
│   └── router.py                 # intent → {SQL, workflow, api_calls, disclaimer}
│
└── frontend/                     # Next.js 14 + TypeScript terminal UI
    ├── package.json
    ├── tsconfig.json
    ├── next.config.mjs
    ├── .env.local.example        # NEXT_PUBLIC_API_BASE
    ├── lib/
    │   ├── api.ts                # typed gateway client
    │   ├── format.ts             # pct/num/sign helpers
    │   └── holdings.ts           # portfolio parser + sample
    ├── components/
    │   ├── NavSidebar.tsx        # 10-item terminal nav
    │   ├── SafetyBanner.tsx      # live/paper/broker/kill-switch state
    │   ├── PageHeader.tsx
    │   ├── Panel.tsx  Badges.tsx  Sparkline.tsx  States.tsx
    └── app/                      # App Router; one route per feature
        ├── layout.tsx  globals.css
        ├── page.tsx                     # 1. Market Dashboard
        ├── research/page.tsx            # 2. Research Lab
        ├── backtest/page.tsx            # 3. Backtest Engine
        ├── factors/page.tsx             # 4. Factor Research
        ├── portfolio/page.tsx           # 5. Portfolio Analytics
        ├── risk/page.tsx                # 6. Risk Command Center
        ├── copilot/page.tsx             # 7. AI Research Copilot
        ├── certification/page.tsx       # 8. Dataset Certification (moat)
        ├── leaderboard/page.tsx         # 9. Strategy Marketplace
        └── audit/page.tsx               # 10. Institutional Audit Trail
```

### Dependencies on the existing repo (unchanged)

```
src/quantfund/research/certification/   # ResearchEligibilityChecker (READ ONLY)
src/quantfund/research/...              # PIT universe, providers, ingestion
reports/research_data_certification.json  # live certification verdict (moat feed)
reports/phase19_strategy_search.json      # leaderboard/funnel feed
reports/pit_universe_coverage.json        # PIT coverage feed
```

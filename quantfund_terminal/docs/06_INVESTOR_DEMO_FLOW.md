# Investor Demo Flow

A tight 8–10 minute narrative that lands the thesis: **the hard, defensible part
of quant is trustworthy data, not another chart.** Everything shown is live from
the running system; nothing is faked.

## Pre-flight (before the room)

```bash
# Terminal A — API gateway (uses the repo's .venv; installs fastapi/uvicorn once)
quantfund_terminal/backend/run.sh          # http://localhost:8000

# Terminal B — UI
cd quantfund_terminal/frontend && npm install && npm run dev   # http://localhost:3000
```
Open `http://localhost:3000`. The green safety banner (Live DISABLED, Kill switch
ARMED) is visible on every screen.

## The narrative (screen by screen)

**0:00 — Hook (Market Dashboard).** "This is a Bloomberg-style terminal for
Indian markets, but the product isn't the dashboard — it's what's behind it."
Show NIFTY/BANKNIFTY, sectors, breadth, movers. Note the `DEMO_SYNTHETIC` badge:
"We label every number's provenance. Watch why that matters."

**1:30 — Research Lab.** Create a momentum strategy with no code (name, family,
lookback, top-N). "Analysts, not engineers, build strategies here."

**2:30 — Backtest Engine.** Run it with explicit costs (10 bps) and slippage
(5 bps). Show the institutional metric set (CAGR/Sharpe/Sortino/MaxDD/Win/PF/
Turnover/Exposure) and the equity + drawdown curves. Then point at the banner:
**"RESULTS ARE ILLUSTRATIVE — dataset is DEVELOPMENT_ONLY."** "Most platforms
would show you this number and call it alpha. We won't."

**4:00 — Factor Research.** Momentum/Quality/Value/LowVol/Size returns, rolling
Sharpe, correlation matrix. Value/Quality are badged `proxy`. "We tell you when a
factor lacks certified fundamentals instead of pretending."

**5:00 — Portfolio & Risk.** Paste a portfolio → beta, VaR, sector exposure,
concentration, then leverage and stress tests (−5%/−10%/−20%). "PMs get risk in
one screen."

**6:00 — AI Research Copilot.** Type "Find momentum stocks." It returns an
**auditable plan**: the SQL it would run, the workflow over our infrastructure,
and the exact API calls — and it filters to `RESEARCH_ELIGIBLE` datasets.
"It plans; it never trades. An LLM plugs in behind the same contract."

**7:00 — THE MOAT (Dataset Certification).** This is the emotional peak. Show
the verdict: **DEVELOPMENT_ONLY**, with the exact blockers (non-exchange source,
PIT coverage 0.0, no ISIN master, no delisting ledger, no verified calendar, no
corporate-action ledger) and the immutable `content_hash`. "This is the honesty
that lets an institution trust us. Our competitors' backtests are survivorship-
biased fiction. Ours fail closed until the data is provably correct."

**8:30 — Strategy Marketplace & Audit.** Leaderboard shows **0 accepted** with a
transparent funnel and prerequisite blockers, DSR gate 0.95, auto-promotion
`false`. Audit shows dataset hash, reproducibility `REPRODUCIBLE`, leakage checks,
`gates_modified=false`. "Every result is reproducible and bound to a hash. No
strategy is ever accepted on uncertified data."

**9:00 — The ask.** "We've built the hard part — the trust layer. With a licensed
NSE/Refinitiv/vendor feed connected, the exact same platform flips to
`RESEARCH_ELIGIBLE` and the leaderboard fills with defensible, reproducible
alpha. That's what the raise funds."

## What we deliberately DON'T do in the demo

- No live or paper trading. No broker connection. No order placement.
- No hand-waving a green "RESEARCH_ELIGIBLE" badge — the current honest state is
  `DEVELOPMENT_ONLY`, and that's the point.
- No fabricated performance presented as real alpha.

## Handling the obvious investor question

> "Your leaderboard is empty and your data is DEVELOPMENT_ONLY — why is that good?"

Because it's the only honest state today, and the platform enforces it
automatically. The moment a certified dataset is connected, nothing else in the
product changes — the gates simply pass. We're selling **trust infrastructure**,
and we can prove it fails closed under scrutiny. That is precisely what an
allocator's diligence team wants to see.

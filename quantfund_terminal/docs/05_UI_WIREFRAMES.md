# UI Wireframes

Dark, monospace "terminal" aesthetic. Persistent left nav (10 features) and a
global safety banner (live/paper/broker/kill-switch) on every screen. Each panel
carries a provenance badge (`RESEARCH_ELIGIBLE` / `DEVELOPMENT_ONLY` /
`DEMO_SYNTHETIC`). ASCII mockups below correspond 1:1 to the implemented pages.

## Global shell

```
┌───────────────┬──────────────────────────────────────────────────────────────┐
│ QUANTFUND     │  <Feature Title>              [badges]   [SAFETY: Live DISABLED│
│ Research Term.│                                           Paper NOT_STARTED ...]│
│               ├──────────────────────────────────────────────────────────────┤
│ 01 Market     │                                                                │
│ 02 Research   │   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────┐ │
│ 03 Backtest   │   │  metric     │ │  metric     │ │  metric     │ │ metric   │ │
│ 04 Factors    │   └─────────────┘ └─────────────┘ └─────────────┘ └──────────┘ │
│ 05 Portfolio  │   ┌───────────────────────────┐ ┌──────────────────────────┐   │
│ 06 Risk       │   │  table / chart            │ │  table / chart           │   │
│ 07 Copilot    │   └───────────────────────────┘ └──────────────────────────┘   │
│ 08 Certif.    │                                                                │
│ 09 Marketplace│   note: data provenance / disclaimer                           │
│ 10 Audit      │                                                                │
└───────────────┴──────────────────────────────────────────────────────────────┘
```

## 1. Market Dashboard

```
[NIFTY50 PROXY]  [BANKNIFTY PROXY]  [BREADTH adv/dec]  [VOLATILITY 20d]
 level 334.6      level 210.4        12 / 8             12.1%
 1D +0.42% v12%   1D -0.10% v15%     A/D 1.5

┌ Sector Performance (1D) ┐ ┌ Top Gainers ┐ ┌ Top Losers ┐
│ IT           +0.51%     │ │ TCS  +1.83% │ │ SBIN -1.42%│
│ Financials   -0.12%     │ │ INFY +1.20% │ │ ITC  -0.98%│
└─────────────────────────┘ └─────────────┘ └────────────┘
note: Synthetic demo data (DEMO_SYNTHETIC). Delayed fallback.
```

## 2. Research Lab

```
┌ Create Strategy (no code) ───────────────────────────────────────────┐
│ Name[________]  Family[momentum▾]  Lookback[126]  TopN[5]  [CREATE]   │
└───────────────────────────────────────────────────────────────────────┘
┌ Strategy Drafts ─────────────────────────────────────────────────────┐
│ ID  Name          Family     Params              Status               │
│ 1   my_mom_v1     momentum   {lookback:126}      DRAFT                 │
└───────────────────────────────────────────────────────────────────────┘
```

## 3. Backtest Engine

```
┌ Configuration ────────────────────────────────────────────────────────┐
│ Family[▾] Universe[__] Start[__] End[__] Lookback[__] TopN[__]          │
│ Rebalance[__] Cost bps[10] Slippage bps[5]           [ RUN BACKTEST ]   │
└─────────────────────────────────────────────────────────────────────────┘
┌ Institutional Report              [DEVELOPMENT_ONLY] ┐
│ CAGR 8.0%  Sharpe 0.42  Sortino 0.55  MaxDD -31%     │
│ Win 52%    PF 1.18      Turnover 0.21  Exposure 1.0  │
│ ⚠ RESULTS ARE ILLUSTRATIVE — dataset is DEVELOPMENT_ONLY │
└──────────────────────────────────────────────────────┘
[ Equity Curve  ~~~~/\~~~/\~~~ ]   [ Drawdown  \___/\__ ]
```

## 4. Factor Research

```
┌ Factor Returns (click to chart) ┐   ┌ Cumulative Long-Short — momentum ┐
│ Factor    Type       AnnRet  SR │   │  ~~~~~/\~~~~/\~~~~~               │
│ momentum  price-based +5%  0.31 │   └───────────────────────────────────┘
│ low_vol   price-based +3%  0.28 │   ┌ Factor Correlations ┐
│ value     proxy       ...       │   │      mom lowv siz ...│
└─────────────────────────────────┘   │ mom  1.0 -0.2 0.1    │
                                       └──────────────────────┘
```

## 5. Portfolio Analytics

```
┌ Paste Portfolio (SYMBOL, weight) ┐  ┌ Summary ─────────────────────────┐
│ RELIANCE, 0.20                    │  │ Beta 0.98  VaR95 -2.1% VaR99 -3.4%│
│ TCS, 0.15                         │  │ MaxDD -28%  HHI 0.11              │
│ ...              [ ANALYZE ]      │  └───────────────────────────────────┘
└───────────────────────────────────┘
┌ Sector Exposure ───────────────┐  ┌ Top Holdings ┐
│ Financials  ████████░░  40%    │  │ RELIANCE 20% │
│ IT          █████░░░░░  25%    │  │ TCS      15% │
└─────────────────────────────────┘  └──────────────┘
```

## 6. Risk Command Center

```
[Gross 1.0][Net 1.0][Leverage 1.0x][Beta 0.98][Vol 18%][VaR95 -2%][Largest 20%]
┌ Stress Tests ───────────────────────────┐ ┌ Sector Concentration ┐
│ Scenario           Shock   Est. PnL      │ │ Financials  40%      │
│ market_down_5pct   -5%     -4.9%         │ │ IT          25%      │
│ market_crash_20pct -20%    -19.6%        │ └──────────────────────┘
└───────────────────────────────────────────┘
```

## 7. AI Research Copilot

```
┌ Ask a research question ─────────────────────────────────────────────┐
│ [ Find momentum stocks____________________________ ]     [ ASK ]       │
│ chips: [Find momentum stocks][Build a low-vol strategy][Explain Sharpe]│
└────────────────────────────────────────────────────────────────────────┘
Intent: find_momentum_stocks (confidence 0.9)
┌ Generated SQL ───────────────┐ ┌ Research Workflow ───────────────────┐
│ SELECT fs.symbol, fs.score   │ │ 1. Resolve PIT universe membership    │
│ FROM factor_scores fs ...    │ │ 2. Compute momentum scores            │
│ WHERE d.certification =      │ │ 3. Filter to certified dataset only   │
│   'RESEARCH_ELIGIBLE' ...    │ │ 4. Return leaders + provenance        │
└───────────────────────────────┘ └───────────────────────────────────────┘
```

## 8. Dataset Certification (moat)

```
┌ Why this is the moat ─────────────────────────────────────────────────┐
│ Most 'quant' platforms backtest on survivorship-biased, CA-naive data.│
│ QuantFund certifies provenance BEFORE any strategy can be accepted.    │
└────────────────────────────────────────────────────────────────────────┘
[Source Grade non_exchange][Data Class DEVELOPMENT_DATA][PIT 0.0][Identity 0.0]
┌ Coverage Dimensions ───────────┐ ┌ Blockers (17) ───────────────────────┐
│ capability_source_bar_ok false │ │ • source_grade=non_exchange ...       │
│ calendar_verified       false  │ │ • membership_coverage_ratio=0.0 < 1.0 │
│ delisted_coverage       unknown│ │ • leakage_safety=false                │
│ content_hash  sha256:8b62...   │ │ ...                                   │
└─────────────────────────────────┘ └────────────────────────────────────────┘
VERDICT:  [ DEVELOPMENT_ONLY ]   (fail-closed; cannot be promoted by the product)
```

## 9. Strategy Marketplace / Leaderboard

```
[Accepted 0][ran_search false][DSR gate 0.95][Auto-promotion false]
┌ Leaderboard ──────────────────────────────────────────────────────────┐
│ Strategy                 Family     CAGR Sharpe MaxDD DSR Status         │
│ Cross-Sectional Momentum momentum   —    —      —     —   BLOCKED_PENDING│
│ Mean Reversion           mean_rev   —    —      —     —   BLOCKED_PENDING│
└──────────────────────────────────────────────────────────────────────────┘
┌ Acceptance Funnel ┐ ┌ Prerequisite Blockers ──────────────────────┐
│ tested 0          │ │ • phase18_research_eligible=false           │
│ accepted 0        │ │ • pit_universe: missing membership ledger   │
└───────────────────┘ └──────────────────────────────────────────────┘
```

## 10. Institutional Audit Trail

```
[Reproducibility REPRODUCIBLE][Dataset Immutable true][Experiments 0]
┌ Dataset Hash ──────────────────────────────────────────┐
│ sha256:8b62214760383a527555bc3046b0799ac39ec2a66169... │
└─────────────────────────────────────────────────────────┘
┌ Leakage & Integrity ─────────┐ ┌ Research Integrity ──────────┐
│ leakage_safe          false  │ │ verdict DEVELOPMENT_ONLY      │
│ pit_universe_enforced true   │ │ fail_closed  true            │
│ next_bar_execution    true   │ │ gates_modified false         │
│ survivorship_protection true │ │ auto_promotion false         │
└───────────────────────────────┘ └───────────────────────────────┘
```

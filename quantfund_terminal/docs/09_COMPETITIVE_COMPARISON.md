# Competitive Comparison

**Positioning:** QuantFund Research Terminal is the *certification-first* research
platform for Indian markets. We don't compete on "most data" or "cheapest charts";
we compete on **provable data trust + reproducible research**, at a fraction of
terminal cost, with India depth the global incumbents treat as an afterthought.

## Feature matrix

| Capability | **QuantFund** | Bloomberg | FactSet | Refinitiv (LSEG) | QuantConnect | TradingView |
|---|---|---|---|---|---|---|
| Primary buyer | Quant research teams | Traders/PMs | Buy-side analysts | Buy/sell-side | Retail→quant devs | Retail traders |
| India-market depth | **Deep, native** | Broad global | Broad global | Broad global | Limited (US-centric) | Broad (charts) |
| **Point-in-time universe / survivorship-safe** | **Core, enforced** | Yes (costly) | Yes | Yes | Partial | No |
| **Dataset certification / eligibility gate** | **Yes (the moat)** | No (data assumed good) | No | No | No | No |
| Provenance badge on every number | **Yes** | Partial | Partial | Partial | No | No |
| Reproducibility (dataset + experiment hash) | **Yes** | No | No | No | Partial | No |
| Leakage / look-ahead controls (next-bar) | **Yes, enforced** | N/A | N/A | N/A | Yes | No |
| No-code strategy builder | **Yes** | Limited | Limited | Limited | Code-first | Pine Script |
| Backtesting engine | **Yes (cost/slippage, institutional metrics)** | Limited | Limited | Limited | **Strong** | Basic |
| Factor research (returns/rolling Sharpe/corr) | **Yes** | Add-ons | **Strong** | Strong | DIY | No |
| Portfolio & risk (VaR/stress/exposure) | **Yes** | **Strong** (PORT) | **Strong** | Strong | DIY | No |
| AI research copilot (auditable plan) | **Yes (gated, plan-only)** | Emerging | Emerging | Emerging | No | No |
| Live/paper trading | **No (by design)** | Yes | Via partners | Via partners | **Yes** | Via brokers |
| Auditability for allocator diligence | **First-class** | Partial | Partial | Partial | Weak | None |
| Approx. cost | **₹/seat SaaS (see model)** | ~$24k+/yr/seat | ~$12k+/yr | ~$12k–22k/yr | $/mo tiers | $/mo tiers |

> Incumbent prices are widely-cited public approximations, not quotes.

## Where each incumbent is strong (and why we still win our niche)

- **Bloomberg Terminal** — unmatched breadth, news, chat, liquidity. But: extremely
  expensive per seat, trader-centric, not a reproducible *research* environment, and
  it does not certify dataset eligibility or expose survivorship/PIT guarantees as a
  gate. We win with India-native, certification-first, reproducible research at a
  fraction of cost.
- **FactSet** — excellent analytics/factor tooling for buy-side analysts. But: global
  generalist, no eligibility gate/provenance-as-product, weaker India quant depth,
  enterprise-heavy sales. We win on trust-as-a-feature and India focus.
- **Refinitiv / LSEG** — vast data + Eikon/Workspace. But: data is assumed-good;
  no certification/fail-closed model; integration-heavy. We turn "is this data safe
  to research on?" into an automatic, auditable verdict.
- **QuantConnect** — best-in-class code-first backtesting/live for (mostly US) devs.
  But: US-centric data, code-required, limited Indian PIT/CA-clean coverage, and no
  certification gate. We serve analysts (no-code) with certified Indian data and an
  eligibility gate they can show diligence teams.
- **TradingView** — superb charts and community for retail. But: not an institutional
  research/backtesting platform, no PIT/survivorship/reproducibility guarantees. Not
  a diligence-grade research tool. Different buyer.

## Our defensible wedge

1. **Certification is a product, not an assumption.** Every dataset carries a
   fail-closed `RESEARCH_ELIGIBLE`/`DEVELOPMENT_ONLY` verdict from an unmodifiable
   checker. No competitor makes data trust a first-class, auditable gate.
2. **Reproducibility by construction.** Dataset + experiment hashes make every
   result independently reproducible — exactly what allocator diligence demands.
3. **India-native depth** (PIT NIFTY membership, ISIN/security master, delistings,
   NSE calendar, corporate actions) that global incumbents underinvest in.
4. **Analyst-first UX** (no-code lab + copilot) at SaaS pricing, not $24k/seat.

## Honest limitations (today)
- We currently have **no** `RESEARCH_ELIGIBLE` dataset connected (demo data is
  synthetic; the repo's certified verdict is `DEVELOPMENT_ONLY`). That is the
  pre-seed milestone, not a claim we're hiding.
- We are not a market-data vendor or a broker. We license authoritative data and
  add the certification/research layer on top.

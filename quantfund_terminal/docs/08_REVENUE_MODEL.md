# Revenue Model

**Thesis:** sell *trustworthy research infrastructure* to Indian institutional and
serious professional quant users. We monetize certified data access + research
tooling (SaaS seats), not trading. Trading is never the business model.

## Who pays

| Segment | Who | Pain we remove | Willingness to pay |
|---|---|---|---|
| Emerging managers / PMS / AIFs | India-focused funds, PMS desks | Survivorship-biased data → blown-up backtests → failed diligence | High |
| Family offices & prop desks | Systematic teams | No affordable PIT/CA-clean Indian data + research stack | High |
| Sell-side & research shops | Analysts building factor/screens | Manual, unreproducible research | Medium-High |
| Quant-savvy professionals | Independent quants, RIAs | QuantConnect lacks clean Indian PIT data; Bloomberg too costly | Medium |
| Universities / researchers | Finance/ML labs | Need citable, reproducible datasets | Low-Medium (land-and-expand) |

## Packaging (SaaS + data-access tiers)

| Plan | Price (illustrative, INR/mo) | Seats | What's included |
|---|---|---|---|
| **Analyst** | ₹8k–₹15k / seat | 1 | Terminal, backtests on 1 certified dataset (delayed), factor research, copilot (plan-only) |
| **Team** | ₹60k–₹1.5L | up to 10 | Everything + shared workspaces, versioning, PDF reports, larger universes, async backtests |
| **Enterprise** | ₹15L–₹60L / yr | custom | SSO/SAML, VPC/data-residency, full certified-data catalog, audit exports, priority support, SLA |
| **Data add-ons** | metered | — | Additional certified datasets (fundamentals, F&O, alt-data), per-dataset or per-query |

> Pricing shown as ranges/illustrative for the model; not a public price list.

## Revenue streams

1. **Seat subscriptions** (primary, recurring). Land with Analyst/Team, expand to Enterprise.
2. **Certified-data access** (recurring + metered). Each dataset is a certified,
   immutable, versioned product; access is licensed per plan or metered per query.
3. **Certified-data marketplace** (Series A+). Third parties publish certified
   datasets; we take a **revenue share** (e.g. 20–30%) and provide the trust layer.
4. **Enterprise deployment & support** (annual contracts, VPC, SLAs).
5. **Professional services** (early-stage only): onboarding a customer's licensed
   feed into the certification pipeline. Deliberately low-margin, used to seed the
   catalog; not a long-term line.

## Unit economics (illustrative targets)

- Blended ACV: ₹1.5L–₹3L (Team) scaling to ₹15L+ (Enterprise).
- Gross margin > 80% (SaaS + content-addressed cacheable data); data licensing
  fees are the main COGS and are passed through/marked up in add-ons.
- CAC payback < 12 months via design-partner-led motion; NRR target > 110% via
  seat + dataset expansion.

## Why the moat compounds revenue

Every certified dataset is a durable, versioned asset with lineage. The catalog
grows monotonically and is expensive to replicate (licensing + engineering +
provenance rigor). Customers standardize their research on our certified lineage,
creating switching costs (their audit trail lives here). The marketplace turns the
moat into a two-sided network at Series A.

## What we will not do
- No brokerage, no order flow monetization, no PFOF, no "signals for sale" that
  imply live trading. The product is research trust, priced as software + data.

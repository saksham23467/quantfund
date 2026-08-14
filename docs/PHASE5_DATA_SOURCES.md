# Phase 5 — Data source / license decision log

**Decision (approved):** D3 = **none for now** — no licensed exchange/paid research package configured in-repo.

## Active sources

| Source | Role | Research eligible? |
|--------|------|--------------------|
| Synthetic fixtures (`tests/fixtures/phase35/`, `tests/fixtures/phase5/`) | CI / demos | **Never** |
| yfinance | Development prototyping only | **Never** |
| NSE calendar `nse_eq_v2023_2025_r1` | Verified session calendar | N/A (calendar, not bars) |
| NIFTY50 `pit_partial_documented_v1` | Partial documented reconstitutions | Insufficient alone (UNKNOWN gaps) |

## Future candidates (not configured)

| Option | Status |
|--------|--------|
| A. NSE official / licensed product | Not licensed in this environment |
| B. Licensed redistributor | Not configured |
| C. Broker historical API | Rejected as default research source |
| Web scraping | Rejected |

## External package path

When a license is obtained:

1. Place package **outside git** (unless redistribution is permitted).
2. Set `QUANTFUND_RESEARCH_PACKAGE=/path/to/package`.
3. Run `make validate-research-package` then `make phase5-demo`.
4. Eligibility remains **derived** — package must not declare `research_eligible`.

## Non-negotiable

- Do not fabricate exchange-grade prints.
- Do not weaken `ResearchEligibilityChecker`.
- Do not commit proprietary RAW bars without redistribution rights.

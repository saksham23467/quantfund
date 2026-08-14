# NIFTY50 PIT membership — `pit_partial_documented_v1`

## What this version is

A **partial**, event-sourced point-in-time membership file containing **only**
NIFTY 50 inclusion/exclusion events that are documented from public NSE Indices
Ltd. reconstitution communications (relayed via SEBI-mandated AMC disclosures).

It is **not** a complete historical NIFTY 50 constituent archive.

## Documented events

| Effective | Action | Symbol | Source |
|-----------|--------|--------|--------|
| 2024-03-28 | Include | SHRIRAMFIN | NSE Indices press release 2024-02-28; AMC SEBI 3.6.8 disclosure |
| 2024-03-28 | Exclude | UPL | same |
| 2024-09-30 | Include | BEL, TRENT | NSE Indices press release 2024-08-23; AMC SEBI 3.6.8 disclosure |
| 2024-09-30 | Exclude | DIVISLAB, LTIM | same |

References:
- https://www.nseindia.com/static/resources/nse-replacements-in-indices-wef-march-28-2024
- Invesco AMC disclosure (Mar 28 2024 change): SEBI Para 3.6.8
- Invesco AMC disclosure (Sep 30 2024 change): SEBI Para 3.6.8

## Coverage semantics

- `completeness = partial_pit`
- `verification_status = partial`
- Names **without** a row in this file → `was_member(...) = UNKNOWN` inside coverage
  (never invent continuous mega-cap membership).
- Names with a documented exit → `FALSE` after `member_to`.
- Names with a documented entry → `TRUE` from `member_from` (if `verified`).

## How to extend (without fabrication)

1. Obtain month-wise Market Cap / Weightage archives from  
   https://www.niftyindices.com/reports/historical-data  
   (“Market Capitalisation, Weightage, Beta for NIFTY 50 & NIFTY Next 50”).
2. Convert archives into interval CSV rows with `verification_status=verified`
   and cite the archive month file in `source`.
3. Publish a **new** `universe_version` (never overwrite this one).

## Explicit non-claims

- Does not list all 50 constituents for any date.
- Does not backfill continuous membership for RELIANCE/TCS/etc. without archives.
- `member_from=2023-01-01` on exit rows is a **coverage floor**, not a verified
  first-inclusion date.

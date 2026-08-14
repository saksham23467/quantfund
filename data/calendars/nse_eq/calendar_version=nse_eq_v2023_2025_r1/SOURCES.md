# NSE_EQ calendar sources — `nse_eq_v2023_2025_r1`

## Source documents

1. **NSE Circular NSE/CMTR/54757** (08 Dec 2022)  
   Trading holidays for the calendar year **2023** (Capital Market Segment).  
   Official archive:  
   https://archives.nseindia.com/content/circulars/CMTR54757.pdf

2. **NSE Circular NSE/CMTR/59124** (27 Oct 2023)  
   Muhurat Trading session on **2023-11-12** (Sunday).  
   Official archive:  
   https://archives.nseindia.com/content/circulars/CMTR59124.pdf

3. **NSE Circular NSE/CMTR/59722** (12 Dec 2023) — 2024 holidays  
4. **NSE Circular NSE/CMTR/65587** (13 Dec 2024) — 2025 holidays  

(See also `nse_eq_v2024_2025_r1/SOURCES.md` for 2024–2025 mirrors.)

## Interpretation rules

- Saturday and Sunday are closed unless a `special_sessions` entry overrides.
- Full holidays from the circular weekday list are closed.
- **Muhurat Trading** days are **OPEN** `special` sessions for daily OHLCV research.
- Weekend-only holiday mentions are informational.

## Coverage

- `effective_start`: 2023-01-01  
- `effective_end`: 2025-12-31  

## Explicit non-claims

- This is **not** the BSE/`XBOM` calendar from `exchange-calendars`.
- Does **not** overwrite `nse_eq_v2024_2025_r1`; that version remains immutable.
- Holidays before 2023 or after 2025 are not included in this version.

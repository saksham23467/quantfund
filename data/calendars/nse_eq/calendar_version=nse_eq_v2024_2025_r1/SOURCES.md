# NSE_EQ calendar sources — `nse_eq_v2024_2025_r1`

## Source documents

1. **NSE Circular NSE/CMTR/59722** (12 Dec 2023)  
   Trading holidays for the calendar year **2024** (Capital Market Segment).  
   Mirror used for audit:  
   https://www.steelcitynettrade.com/Circulars/Trading%20holidays%20for%20the%20calendar%20year%202024.pdf  
   Official holidays page:  
   https://www.nseindia.com/resources/exchange-communication-holidays

2. **NSE Circular NSE/CMTR/65587** (13 Dec 2024)  
   Trading holidays for the calendar year **2025** (Capital Market Segment).  
   Mirror used for audit:  
   https://www.steelcitynettrade.com/Circulars/NSE-Trading%20holidays%20for%20the%20calendar%20year%202025.pdf

## Interpretation rules encoded in this version

- Saturday and Sunday are closed unless a `special_sessions` entry overrides.
- Full holidays from the circular weekday list are closed.
- **Muhurat Trading** days (Diwali Laxmi Pujan with Muhurat footnote) are **OPEN** `special` sessions for daily OHLCV research, because the exchange conducts a trading session that day.
- Weekend-only holiday mentions are informational (already closed as weekend).

## Coverage

- `effective_start`: 2024-01-01  
- `effective_end`: 2025-12-31  

Dates outside this range are **out of coverage** and must not be treated as verified NSE sessions.

## Explicit non-claims

- This is **not** the BSE/`XBOM` calendar from `exchange-calendars`.
- Holidays before 2024 or after 2025 are not included in this version.

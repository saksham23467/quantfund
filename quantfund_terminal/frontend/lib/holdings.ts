// Parse a "SYMBOL,weight" (or "SYMBOL weight") textarea into holdings.
export function parseHoldings(text: string): { symbol: string; weight: number }[] {
  return text
    .split(/\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const [sym, w] = l.split(/[\s,]+/);
      return { symbol: sym.toUpperCase(), weight: parseFloat(w) };
    })
    .filter((h) => h.symbol && !Number.isNaN(h.weight));
}

export const SAMPLE_PORTFOLIO = `RELIANCE, 0.20
TCS, 0.15
HDFCBANK, 0.15
ICICIBANK, 0.10
INFY, 0.10
ITC, 0.10
LT, 0.08
MARUTI, 0.07
SUNPHARMA, 0.05`;

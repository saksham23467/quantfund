export const pct = (x: number | null | undefined, digits = 2): string =>
  x === null || x === undefined || Number.isNaN(x)
    ? "—"
    : `${(x * 100).toFixed(digits)}%`;

export const num = (x: number | null | undefined, digits = 2): string =>
  x === null || x === undefined || Number.isNaN(x) ? "—" : x.toFixed(digits);

export const signClass = (x: number | null | undefined): string =>
  x === null || x === undefined ? "" : x >= 0 ? "pos" : "neg";

// Indian numbering: crore (1e7) / lakh (1e5).
export const inr = (x: number | null | undefined): string => {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  if (Math.abs(x) >= 1e7) return `₹${(x / 1e7).toFixed(2)} Cr`;
  if (Math.abs(x) >= 1e5) return `₹${(x / 1e5).toFixed(2)} L`;
  return `₹${x.toLocaleString("en-IN")}`;
};

export const usd = (x: number | null | undefined): string => {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  if (Math.abs(x) >= 1e9) return `$${(x / 1e9).toFixed(1)}B`;
  if (Math.abs(x) >= 1e6) return `$${(x / 1e6).toFixed(1)}M`;
  return `$${x.toLocaleString("en-US")}`;
};

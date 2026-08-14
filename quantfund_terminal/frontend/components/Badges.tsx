export function VerdictBadge({ verdict }: { verdict?: string }) {
  const v = (verdict ?? "").toUpperCase();
  if (v === "RESEARCH_ELIGIBLE")
    return <span className="badge eligible">RESEARCH_ELIGIBLE</span>;
  return <span className="badge dev">DEVELOPMENT_ONLY</span>;
}

export function StatusBadge({ status }: { status?: string }) {
  const s = (status ?? "").toUpperCase();
  if (s.includes("ACCEPT")) return <span className="badge eligible">{s}</span>;
  if (s.includes("REJECT") || s.includes("BLOCKED"))
    return <span className="badge blocked">{s}</span>;
  return <span className="badge demo">{s || "RESEARCH_ONLY"}</span>;
}

export function DataClassBadge({ dataClass }: { dataClass?: string }) {
  return <span className="badge demo">{dataClass ?? "DEMO_SYNTHETIC"}</span>;
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { PERSONAS, getPersona, setPersona } from "@/lib/persona";

const RESEARCH: { href: string; label: string }[] = [
  { href: "/", label: "Market Dashboard" },
  { href: "/research", label: "Research Lab" },
  { href: "/backtest", label: "Backtest Engine" },
  { href: "/factors", label: "Factor Research" },
  { href: "/portfolio", label: "Portfolio Analytics" },
  { href: "/risk", label: "Risk Command Center" },
  { href: "/copilot", label: "AI Research Copilot" },
];

const PLATFORM: { href: string; label: string }[] = [
  { href: "/exchange", label: "Dataset Exchange" },
  { href: "/marketplace", label: "Strategy Marketplace" },
  { href: "/studio", label: "Analytics Studio" },
  { href: "/certification", label: "Dataset Certification" },
  { href: "/audit", label: "Audit Trail" },
  { href: "/investor", label: "Investor Dashboard" },
];

export function NavSidebar() {
  const path = usePathname();
  const [label, setLabel] = useState(PERSONAS[0].label);

  useEffect(() => {
    setLabel(getPersona().label);
  }, []);

  function onPersona(e: React.ChangeEvent<HTMLSelectElement>) {
    const p = PERSONAS.find((x) => x.label === e.target.value);
    if (p) {
      setPersona(p);
      window.location.reload();
    }
  }

  const item = (it: { href: string; label: string }, i: number) => {
    const active = it.href === "/" ? path === "/" : path.startsWith(it.href);
    return (
      <Link key={it.href} href={it.href} className={active ? "active" : ""}>
        <span className="idx">{String(i + 1).padStart(2, "0")}</span>
        {it.label}
      </Link>
    );
  };

  return (
    <aside className="sidebar">
      <div className="brand">
        QUANTFUND
        <small>Research Terminal v2 · Indian Markets</small>
      </div>

      <div className="nav-section">Research</div>
      <nav className="nav">{RESEARCH.map(item)}</nav>

      <div className="nav-section">Platform</div>
      <nav className="nav">{PLATFORM.map((it, i) => item(it, i + RESEARCH.length))}</nav>

      <div className="persona">
        <label>Signed in as</label>
        <select value={label} onChange={onPersona}>
          {PERSONAS.map((p) => (
            <option key={p.label} value={p.label}>
              {p.label}
            </option>
          ))}
        </select>
      </div>
    </aside>
  );
}

"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Sparkline } from "@/components/Sparkline";
import { DataClassBadge } from "@/components/Badges";
import { Loading, Offline } from "@/components/States";
import { getFactors } from "@/lib/api";
import { num, pct } from "@/lib/format";

export default function FactorsPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string>("momentum");

  useEffect(() => {
    getFactors(126).then(setD).catch((e) => setErr(String(e)));
  }, []);
  if (err) return <Offline title="Factor Research" err={err} />;
  if (!d) return <Loading title="Factor Research" />;

  const selected = d.factors.find((f: any) => f.factor === sel);
  const factors: string[] = d.factors.map((f: any) => f.factor);

  return (
    <>
      <PageHeader title="Factor Research">
        <DataClassBadge dataClass={d.data_class} />
      </PageHeader>

      <Panel title="Factor Returns">
        <table>
          <thead><tr><th>Factor</th><th>Type</th><th>Ann. Return</th><th>Sharpe</th></tr></thead>
          <tbody>
            {d.factors.map((f: any) => (
              <tr key={f.factor} onClick={() => setSel(f.factor)} style={{ cursor: "pointer" }}>
                <td className={f.factor === sel ? "accent" : ""}>{f.factor}</td>
                <td className="muted">{f.is_proxy ? "proxy" : "price-based"}</td>
                <td className={f.annualized_return >= 0 ? "pos" : "neg"}>{pct(f.annualized_return)}</td>
                <td>{num(f.sharpe)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {selected && (
        <Panel title={`Cumulative Long-Short — ${selected.factor}`}>
          <Sparkline data={selected.cumulative.map((p: any) => p.value)} />
        </Panel>
      )}

      <Panel title="Factor Correlations">
        <table>
          <thead>
            <tr><th></th>{factors.map((f) => <th key={f}>{f.slice(0, 4)}</th>)}</tr>
          </thead>
          <tbody>
            {factors.map((r) => (
              <tr key={r}>
                <td className="muted">{r}</td>
                {factors.map((c) => {
                  const v = d.correlations?.[r]?.[c];
                  return (
                    <td key={c} className={v > 0 ? "pos" : v < 0 ? "neg" : ""}>
                      {v === undefined || v === null ? "—" : num(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <p className="note">{d.disclaimer}</p>
    </>
  );
}

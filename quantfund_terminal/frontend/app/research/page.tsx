"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/Badges";
import { createStrategy, listStrategies } from "@/lib/api";

const FAMILIES = ["momentum", "trend", "mean_reversion", "breakout", "volatility"];

export default function ResearchLab() {
  const [name, setName] = useState("");
  const [family, setFamily] = useState("momentum");
  const [lookback, setLookback] = useState(126);
  const [topN, setTopN] = useState(5);
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    try {
      setData(await listStrategies());
    } catch (e) {
      setErr(String(e));
    }
  }
  useEffect(() => {
    refresh();
  }, []);

  async function create() {
    if (!name) return;
    await createStrategy({ name, family, params: { lookback, holding_top_n: topN } });
    setName("");
    refresh();
  }

  return (
    <>
      <PageHeader title="Research Lab" />

      <Panel title="Create Strategy (no code)">
        <div className="row">
          <div className="field"><label>Name</label><input value={name} onChange={(e) => setName(e.target.value)} placeholder="my_momentum_v1" /></div>
          <div className="field"><label>Family</label>
            <select value={family} onChange={(e) => setFamily(e.target.value)}>
              {FAMILIES.map((f) => <option key={f}>{f}</option>)}
            </select>
          </div>
          <div className="field"><label>Lookback</label><input type="number" value={lookback} onChange={(e) => setLookback(+e.target.value)} /></div>
          <div className="field"><label>Top N</label><input type="number" value={topN} onChange={(e) => setTopN(+e.target.value)} /></div>
          <div className="field"><label>&nbsp;</label><button className="primary" onClick={create}>CREATE DRAFT</button></div>
        </div>
        <p className="note">
          Drafts are never auto-run and never accepted without a research-eligible dataset. Run them
          from the Backtest Engine; acceptance is gated by Dataset Certification.
        </p>
      </Panel>

      {err && <Panel title="Error"><div className="mono-block">{err}</div></Panel>}

      <Panel title="Strategy Drafts">
        <table>
          <thead><tr><th>ID</th><th>Name</th><th>Family</th><th>Params</th><th>Status</th></tr></thead>
          <tbody>
            {(data?.strategies ?? []).length === 0 && (
              <tr><td colSpan={5} className="note">No drafts yet.</td></tr>
            )}
            {(data?.strategies ?? []).map((s: any) => (
              <tr key={s.id}>
                <td>{s.id}</td>
                <td>{s.name}</td>
                <td className="muted">{s.family}</td>
                <td><code>{JSON.stringify(s.params)}</code></td>
                <td><StatusBadge status={s.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </>
  );
}

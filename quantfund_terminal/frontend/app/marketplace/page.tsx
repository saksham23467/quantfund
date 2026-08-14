"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { StatusBadge } from "@/components/Badges";
import { Loading, Offline } from "@/components/States";
import { getMarketplace, getProof } from "@/lib/api";
import { num, pct } from "@/lib/format";

export default function MarketplacePage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [proof, setProof] = useState<any>(null);

  useEffect(() => {
    getMarketplace().then(setD).catch((e) => setErr(String(e)));
  }, []);
  if (err) return <Offline title="Strategy Marketplace" err={err} />;
  if (!d) return <Loading title="Strategy Marketplace" />;

  const gated = d.authoritative_gated;
  const demo = d.demo_leaderboard;

  async function showProof(id: number) {
    setProof({ loading: true });
    try {
      setProof(await getProof(id));
    } catch (e) {
      setProof({ error: String(e) });
    }
  }

  return (
    <>
      <PageHeader title="Strategy Marketplace" />

      <div className="grid cols-3">
        <Panel title="Authoritative — Accepted"><Metric label="on certified data" value={gated.accepted_count} cls={gated.accepted_count ? "pos" : "warn"} /></Panel>
        <Panel title="DSR Gate"><Metric label="dsr_min" value={num(gated.gate_policy?.dsr_min, 2)} /></Panel>
        <Panel title="Demo Strategies"><Metric label="illustrative" value={demo.count} cls="demo" /></Panel>
      </div>

      <Panel title="Marketplace Leaderboard (illustrative — DEMO_SYNTHETIC)">
        <table>
          <thead>
            <tr><th>Strategy</th><th>Family</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>Max DD</th><th>Status</th><th>Proof</th></tr>
          </thead>
          <tbody>
            {demo.rows.map((r: any) => (
              <tr key={r.backtest_id}>
                <td>{r.strategy}</td>
                <td className="muted">{r.family}</td>
                <td className={(r.cagr ?? 0) >= 0 ? "pos" : "neg"}>{pct(r.cagr)}</td>
                <td>{num(r.sharpe)}</td>
                <td>{num(r.sortino)}</td>
                <td className="neg">{pct(r.max_drawdown)}</td>
                <td><StatusBadge status={r.status} /></td>
                <td><button onClick={() => showProof(r.backtest_id)}>verify</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">{demo.note}</p>
      </Panel>

      {proof && (
        <Panel title="Reproducibility Proof">
          {proof.loading && <div className="note">Recomputing…</div>}
          {proof.error && <div className="mono-block">{proof.error}</div>}
          {proof.backtest_id && (
            <>
              <div className="grid cols-3">
                <Metric label="Reproducible" value={String(proof.reproducible)} cls={proof.reproducible ? "pos" : "neg"} />
                <Metric label="Stored Sharpe" value={num(proof.stored_metrics?.sharpe)} />
                <Metric label="Recomputed Sharpe" value={num(proof.recomputed_metrics?.sharpe)} />
              </div>
              <div className="mono-block" style={{ marginTop: 10 }}>
                dataset_hash:    {proof.dataset_hash}{"\n"}
                experiment_hash: {proof.experiment_hash}{"\n"}
                recomputed_hash: {proof.recomputed_experiment_hash}{"\n"}
                record_hash:     {proof.research_record?.content_hash ?? "—"}
              </div>
              <p className="note">{proof.note}</p>
            </>
          )}
        </Panel>
      )}

      <Panel title="Authoritative Prerequisite Blockers">
        <ul className="list">
          {(gated.prerequisite?.blockers ?? []).map((b: string, i: number) => (
            <li key={i} className="neg">{b}</li>
          ))}
        </ul>
        <p className="note">{gated.statement}</p>
      </Panel>
    </>
  );
}

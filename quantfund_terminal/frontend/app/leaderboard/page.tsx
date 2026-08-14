"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { StatusBadge } from "@/components/Badges";
import { Loading, Offline } from "@/components/States";
import { getLeaderboard } from "@/lib/api";
import { num, pct } from "@/lib/format";

export default function LeaderboardPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getLeaderboard().then(setD).catch((e) => setErr(String(e)));
  }, []);
  if (err) return <Offline title="Strategy Marketplace" err={err} />;
  if (!d) return <Loading title="Strategy Marketplace" />;

  const f = d.funnel ?? {};
  return (
    <>
      <PageHeader title="Strategy Marketplace" />

      <div className="grid cols-4">
        <Panel title="Accepted"><Metric label="strategies" value={d.accepted_count} cls={d.accepted_count ? "pos" : "warn"} /></Panel>
        <Panel title="Search"><Metric label="ran_search" value={String(d.ran_search)} cls="warn" /></Panel>
        <Panel title="DSR gate"><Metric label="dsr_min" value={num(d.gate_policy?.dsr_min, 2)} /></Panel>
        <Panel title="Auto-promotion"><Metric label="enabled" value={String(d.auto_promotion?.enabled)} cls="pos" /></Panel>
      </div>

      <Panel title="Leaderboard">
        <table>
          <thead>
            <tr><th>Strategy</th><th>Family</th><th>CAGR</th><th>Sharpe</th><th>Max DD</th><th>DSR</th><th>Status</th></tr>
          </thead>
          <tbody>
            {d.rows.map((r: any, i: number) => (
              <tr key={i}>
                <td>{r.strategy}</td>
                <td className="muted">{r.family}</td>
                <td>{r.cagr === null ? "—" : pct(r.cagr)}</td>
                <td>{r.sharpe === null ? "—" : num(r.sharpe)}</td>
                <td>{r.max_drawdown === null ? "—" : pct(r.max_drawdown)}</td>
                <td>{r.dsr === null ? "—" : num(r.dsr)}</td>
                <td><StatusBadge status={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">{d.statement}</p>
      </Panel>

      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <Panel title="Acceptance Funnel">
          <table>
            <tbody>
              {Object.entries(f).map(([k, v]: any) => (
                <tr key={k}><td>{k}</td><td style={{ textAlign: "right" }}>{v}</td></tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Prerequisite Blockers">
          <ul className="list">
            {(d.prerequisite?.blockers ?? []).map((b: string, i: number) => (
              <li key={i} className="neg">{b}</li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  );
}

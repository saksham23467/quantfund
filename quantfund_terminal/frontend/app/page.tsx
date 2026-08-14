"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { DataClassBadge } from "@/components/Badges";
import { Loading, Offline } from "@/components/States";
import { getMarket } from "@/lib/api";
import { num } from "@/lib/format";

export default function MarketDashboard() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getMarket().then(setD).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <Offline title="Market Dashboard" err={err} />;
  if (!d) return <Loading title="Market Dashboard" />;

  const idx = d.indices;
  return (
    <>
      <PageHeader title="Market Dashboard">
        <DataClassBadge dataClass={d.data_class} />
        <span className="badge demo">{d.mode}</span>
      </PageHeader>

      <div className="grid cols-4">
        <Panel title="NIFTY 50 (proxy)">
          <Metric label="Level" value={num(idx.NIFTY50_PROXY.level)} />
          <div className="note">
            1D <span className={idx.NIFTY50_PROXY.change_pct_1d >= 0 ? "pos" : "neg"}>
              {num(idx.NIFTY50_PROXY.change_pct_1d)}%
            </span> · vol {num(idx.NIFTY50_PROXY.annualized_vol_20d)}%
          </div>
        </Panel>
        <Panel title="BANKNIFTY (proxy)">
          <Metric label="Level" value={num(idx.BANKNIFTY_PROXY.level)} />
          <div className="note">
            1D <span className={idx.BANKNIFTY_PROXY.change_pct_1d >= 0 ? "pos" : "neg"}>
              {num(idx.BANKNIFTY_PROXY.change_pct_1d)}%
            </span> · vol {num(idx.BANKNIFTY_PROXY.annualized_vol_20d)}%
          </div>
        </Panel>
        <Panel title="Breadth">
          <Metric label="Adv / Dec" value={`${d.breadth.advancers} / ${d.breadth.decliners}`} />
          <div className="note">A/D ratio {num(d.breadth.advance_decline_ratio)}</div>
        </Panel>
        <Panel title="Volatility">
          <Metric
            label="NIFTY proxy (ann. 20d)"
            value={`${num(d.volatility.nifty_proxy_annualized_20d)}%`}
          />
        </Panel>
      </div>

      <div className="grid cols-3" style={{ marginTop: 14 }}>
        <Panel title="Sector Performance (1D)">
          <table>
            <tbody>
              {Object.entries(d.sector_performance).map(([s, v]: any) => (
                <tr key={s}>
                  <td>{s}</td>
                  <td className={v >= 0 ? "pos" : "neg"} style={{ textAlign: "right" }}>
                    {num(v)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Top Gainers">
          <Movers rows={d.top_gainers} />
        </Panel>
        <Panel title="Top Losers">
          <Movers rows={d.top_losers} />
        </Panel>
      </div>

      <p className="note">{d.disclaimer}</p>
    </>
  );
}

function Movers({ rows }: { rows: any[] }) {
  return (
    <table>
      <tbody>
        {rows.map((r) => (
          <tr key={r.symbol}>
            <td>{r.symbol}</td>
            <td className={r.change_pct >= 0 ? "pos" : "neg"} style={{ textAlign: "right" }}>
              {num(r.change_pct)}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { Loading, Offline } from "@/components/States";
import { getInvestor } from "@/lib/api";
import { inr, usd } from "@/lib/format";

export default function InvestorPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getInvestor().then(setD).catch((e) => setErr(String(e)));
  }, []);
  if (err) return <Offline title="Investor Dashboard" err={err} />;
  if (!d) return <Loading title="Investor Dashboard" />;

  const s = d.saas_metrics;
  const moat = d.dataset_moat;

  return (
    <>
      <PageHeader title="Investor Dashboard" />

      <div className="grid cols-4">
        <Panel title="ARR"><Metric label="annual recurring" value={inr(s.arr_inr)} cls="pos" /></Panel>
        <Panel title="MRR"><Metric label="monthly recurring" value={inr(s.mrr_inr)} cls="pos" /></Panel>
        <Panel title="Orgs"><Metric label="tenants" value={s.orgs} /></Panel>
        <Panel title="Seats"><Metric label="paid seats" value={s.seats} /></Panel>
      </div>

      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <Panel title="Revenue by Plan">
          <table>
            <thead><tr><th>Plan</th><th>Orgs</th><th>Seats</th><th>MRR</th></tr></thead>
            <tbody>
              {Object.entries(s.by_plan).map(([plan, v]: any) => (
                <tr key={plan}>
                  <td>{plan}</td><td>{v.orgs}</td><td>{v.seats}</td><td>{inr(v.mrr_inr)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note">ARPA: {inr(s.arpa_inr)} · {d.traction_note}</p>
        </Panel>

        <Panel title="Dataset Moat">
          <div className="grid cols-3">
            <Metric label="Catalog" value={moat.datasets_in_catalog} />
            <Metric label="Certified" value={moat.research_eligible} cls={moat.research_eligible ? "pos" : "warn"} />
            <Metric label="Dev-only" value={moat.development_only} cls="warn" />
          </div>
          <p className="note">{moat.why_moat}</p>
        </Panel>
      </div>

      <Panel title="Total Addressable Market (estimates)">
        <table>
          <thead><tr><th>Segment</th><th>Size</th><th>Basis</th></tr></thead>
          <tbody>
            {d.tam.segments.map((seg: any) => (
              <tr key={seg.name}>
                <td>{seg.name}</td>
                <td className="accent">{usd(seg.size)}</td>
                <td className="muted">{seg.basis}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">{d.tam.disclaimer}</p>
      </Panel>

      <Panel title="Competitive Comparison">
        <table>
          <thead>
            <tr><th>Platform</th><th>India Depth</th><th>Cert Gate</th><th>Reproducible</th><th>No-code</th><th>Approx Cost</th><th>Our Edge</th></tr>
          </thead>
          <tbody>
            {d.competitive_comparison.map((c: any) => (
              <tr key={c.name}>
                <td>{c.name}</td>
                <td className="muted">{c.india_depth}</td>
                <td className={c.certification_gate ? "pos" : "neg"}>{c.certification_gate ? "yes" : "no"}</td>
                <td className={c.reproducibility === true ? "pos" : c.reproducibility === "partial" ? "warn" : "neg"}>{String(c.reproducibility)}</td>
                <td className="muted">{c.no_code_research}</td>
                <td className="muted">{c.approx_cost}</td>
                <td className="accent" style={{ fontSize: 11 }}>{c.our_edge}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">
          QuantFund row (reference): India depth <span className="pos">deep</span> · Cert gate <span className="pos">yes</span> ·
          Reproducible <span className="pos">yes</span> · No-code <span className="pos">yes</span> · SaaS pricing.
        </p>
      </Panel>
    </>
  );
}

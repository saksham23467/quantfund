"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { VerdictBadge } from "@/components/Badges";
import { Loading, Offline } from "@/components/States";
import { getDatasets } from "@/lib/api";

export default function ExchangePage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    getDatasets().then(setD).catch((e) => setErr(String(e)));
  }, []);
  if (err) return <Offline title="Research Dataset Exchange" err={err} />;
  if (!d) return <Loading title="Research Dataset Exchange" />;

  return (
    <>
      <PageHeader title="Research Dataset Exchange" />

      <div className="grid cols-3">
        <Panel title="Catalog"><Metric label="datasets" value={d.count} /></Panel>
        <Panel title="Research Eligible"><Metric label="certified" value={d.research_eligible_count} cls={d.research_eligible_count ? "pos" : "warn"} /></Panel>
        <Panel title="Development Only"><Metric label="fail-closed" value={d.development_only_count} cls="warn" /></Panel>
      </div>

      <Panel title="Datasets">
        <table>
          <thead>
            <tr><th>Dataset</th><th>Source</th><th>Type</th><th>Grade</th><th>Data Class</th><th>Coverage</th><th>Verdict</th></tr>
          </thead>
          <tbody>
            {d.datasets.map((ds: any) => (
              <>
                <tr key={ds.dataset_id} onClick={() => setOpen(open === ds.dataset_id ? null : ds.dataset_id)} style={{ cursor: "pointer" }}>
                  <td>{ds.title}<div className="muted" style={{ fontSize: 10 }}>{ds.dataset_id} · {ds.version}</div></td>
                  <td className="muted">{ds.source_name}</td>
                  <td>{ds.source_type}</td>
                  <td className={ds.source_grade === "exchange" || ds.source_grade === "research" ? "pos" : "warn"}>{ds.source_grade}</td>
                  <td className="muted">{ds.data_class}</td>
                  <td className="muted">{ds.coverage.start ?? "—"} → {ds.coverage.end ?? "—"}</td>
                  <td><VerdictBadge verdict={ds.certification.verdict} /></td>
                </tr>
                {open === ds.dataset_id && (
                  <tr key={ds.dataset_id + "-x"}>
                    <td colSpan={7} style={{ background: "var(--panel-2)" }}>
                      <div className="grid cols-2">
                        <div>
                          <div className="note">Provenance</div>
                          <div className="mono-block">content_hash: {ds.content_hash}{"\n"}immutable: {String(ds.immutable)}{"\n"}object_uri: {ds.object_uri ?? "—"}</div>
                          <div className="note" style={{ marginTop: 8 }}>Coverage dimensions</div>
                          <table><tbody>
                            <Row k="membership_coverage_ratio" v={ds.certification.membership_coverage_ratio} />
                            <Row k="instrument_identity_coverage" v={ds.certification.instrument_identity_coverage} />
                            <Row k="delisted_coverage" v={ds.certification.delisted_coverage} />
                            <Row k="corporate_action_coverage" v={ds.certification.corporate_action_coverage} />
                            <Row k="calendar_verified" v={String(ds.certification.calendar_verified)} />
                            <Row k="leakage_safe" v={String(ds.certification.leakage_safe)} />
                          </tbody></table>
                        </div>
                        <div>
                          <div className="note">Blockers ({ds.certification.blockers?.length ?? 0})</div>
                          <ul className="list">
                            {(ds.certification.blockers ?? []).map((b: string, i: number) => (
                              <li key={i} className="neg">{b}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </Panel>

      <p className="note">{d.note}</p>
    </>
  );
}

function Row({ k, v }: { k: string; v: any }) {
  return (
    <tr><td>{k}</td><td style={{ textAlign: "right" }}>{v ?? "—"}</td></tr>
  );
}

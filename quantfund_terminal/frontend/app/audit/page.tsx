"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { Loading, Offline } from "@/components/States";
import { getAudit } from "@/lib/api";

export default function AuditPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getAudit().then(setD).catch((e) => setErr(String(e)));
  }, []);
  if (err) return <Offline title="Audit Trail" err={err} />;
  if (!d) return <Loading title="Audit Trail" />;

  const leak = d.leakage_checks ?? {};
  const integ = d.research_integrity ?? {};
  return (
    <>
      <PageHeader title="Institutional Audit Trail" />

      <div className="grid cols-3">
        <Panel title="Reproducibility"><Metric label="status" value={d.reproducibility_status} cls="pos" /></Panel>
        <Panel title="Dataset Immutable"><Metric label="immutable" value={String(d.dataset_immutable)} cls="pos" /></Panel>
        <Panel title="Experiments Recorded"><Metric label="count" value={d.experiments_recorded} /></Panel>
      </div>

      <Panel title="Dataset Hash">
        <div className="mono-block">{d.dataset_hash ?? "—"}</div>
      </Panel>

      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <Panel title="Leakage & Integrity Checks">
          <table>
            <tbody>
              <Row k="leakage_safe" v={leak.leakage_safe} />
              <Row k="pit_universe_enforced" v={leak.pit_universe_enforced} />
              <Row k="next_bar_execution" v={leak.next_bar_execution} />
              <Row k="survivorship_protection" v={leak.survivorship_protection} />
            </tbody>
          </table>
        </Panel>
        <Panel title="Research Integrity">
          <table>
            <tbody>
              <Row k="verdict" v={integ.verdict} />
              <Row k="research_eligible" v={integ.research_eligible} />
              <Row k="fail_closed" v={integ.fail_closed} />
              <Row k="gates_modified" v={integ.gates_modified} />
              <Row k="auto_promotion" v={integ.auto_promotion} />
            </tbody>
          </table>
        </Panel>
      </div>

      <p className="note">{d.statement}</p>
    </>
  );
}

function Row({ k, v }: { k: string; v: any }) {
  const cls = v === true ? "pos" : v === false ? "neg" : "";
  return (
    <tr>
      <td>{k}</td>
      <td style={{ textAlign: "right" }} className={cls}>{String(v)}</td>
    </tr>
  );
}

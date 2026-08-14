"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { VerdictBadge } from "@/components/Badges";
import { Loading, Offline } from "@/components/States";
import { getCertification } from "@/lib/api";

export default function CertificationPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getCertification().then(setD).catch((e) => setErr(String(e)));
  }, []);
  if (err) return <Offline title="Dataset Certification" err={err} />;
  if (!d) return <Loading title="Dataset Certification" />;

  const dim = d.dimensions ?? {};
  return (
    <>
      <PageHeader title="Dataset Certification">
        <VerdictBadge verdict={d.verdict} />
      </PageHeader>

      <Panel title="Why this is the moat">
        <div className="note" style={{ fontSize: 12 }}>{d.why_it_matters}</div>
      </Panel>

      <div className="grid cols-4" style={{ marginTop: 14 }}>
        <Panel title="Source Grade"><Metric label="grade" value={dim.source_grade ?? "—"} cls="warn" /></Panel>
        <Panel title="Data Class"><Metric label="class" value={d.data_class ?? "—"} cls="warn" /></Panel>
        <Panel title="PIT Membership"><Metric label="coverage ratio" value={dim.membership_coverage_ratio ?? 0} cls="neg" /></Panel>
        <Panel title="Identity Coverage"><Metric label="ISIN coverage" value={dim.instrument_identity_coverage ?? 0} cls="neg" /></Panel>
      </div>

      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <Panel title="Coverage Dimensions">
          <table>
            <tbody>
              <Row k="capability_source_bar_ok" v={String(dim.capability_source_bar_ok)} />
              <Row k="calendar_verified" v={String(dim.calendar_quality?.calendar_verified)} />
              <Row k="calendar_errors" v={String(dim.calendar_quality?.calendar_errors)} />
              <Row k="delisted_coverage" v={dim.delisted_coverage} />
              <Row k="corporate_action_coverage" v={dim.corporate_action_coverage} />
              <Row k="leakage_safe" v={String(d.leakage_safe)} />
              <Row k="reproducible" v={String(d.reproducible)} />
              <Row k="immutable" v={String(d.immutable)} />
              <Row k="content_hash" v={d.content_hash} mono />
            </tbody>
          </table>
        </Panel>
        <Panel title={`Blockers (${d.blockers?.length ?? 0})`}>
          <ul className="list">
            {(d.blockers ?? []).map((b: string, i: number) => (
              <li key={i} className="neg">{b}</li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel title="Capability Gaps (what a research-grade source must provide)">
        <ul className="list">
          {(d.capability_gaps ?? []).map((g: string, i: number) => (
            <li key={i} className="warn">{g}</li>
          ))}
        </ul>
      </Panel>

      <p className="note">
        Verdict is produced by the unmodified <code>ResearchEligibilityChecker</code>. The product
        layer only reads it; it cannot promote a dataset. Generated at {d.generated_at}.
      </p>
    </>
  );
}

function Row({ k, v, mono }: { k: string; v?: string; mono?: boolean }) {
  return (
    <tr>
      <td>{k}</td>
      <td style={{ textAlign: "right" }} className={mono ? "accent" : ""}>
        {mono ? <code>{v}</code> : v ?? "—"}
      </td>
    </tr>
  );
}

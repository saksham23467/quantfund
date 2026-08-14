"use client";

import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { askCopilot } from "@/lib/api";

const EXAMPLES = [
  "Find momentum stocks",
  "Build a low-vol strategy",
  "Explain why Sharpe fell",
  "Run a breakout backtest",
  "Is this dataset research eligible?",
];

export default function CopilotPage() {
  const [prompt, setPrompt] = useState("Find momentum stocks");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask(p?: string) {
    const q = p ?? prompt;
    setPrompt(q);
    setBusy(true);
    setErr(null);
    try {
      setRes(await askCopilot(q));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="AI Research Copilot" />

      <Panel title="Ask a research question">
        <div className="row">
          <input style={{ flex: 1, minWidth: 360 }} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
          <button className="primary" onClick={() => ask()} disabled={busy}>{busy ? "PLANNING…" : "ASK"}</button>
        </div>
        <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
          {EXAMPLES.map((e) => (
            <button key={e} onClick={() => ask(e)}>{e}</button>
          ))}
        </div>
        <p className="note">
          The copilot returns an auditable PLAN (SQL + workflow over existing infrastructure). It
          executes nothing and can never place an order. An LLM can be plugged in behind the same
          contract.
        </p>
      </Panel>

      {err && <Panel title="Error"><div className="mono-block">{err}</div></Panel>}

      {res && (
        <>
          <Panel title={`Intent: ${res.intent} (confidence ${res.confidence})`}>
            <div className="note" style={{ fontSize: 12, color: "var(--text)" }}>{res.summary}</div>
          </Panel>
          <div className="grid cols-2">
            <Panel title="Generated SQL">
              <div className="mono-block">{res.generated_sql}</div>
            </Panel>
            <Panel title="Research Workflow">
              <ol className="list">
                {res.workflow_steps.map((s: string, i: number) => <li key={i}>{s}</li>)}
              </ol>
            </Panel>
          </div>
          <Panel title="API Calls">
            <div className="mono-block">{(res.api_calls ?? []).join("\n") || "—"}</div>
            <p className="note">{res.disclaimer} · {res.safety_note}</p>
          </Panel>
        </>
      )}
    </>
  );
}

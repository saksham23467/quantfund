"use client";

import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { analyzeRisk } from "@/lib/api";
import { parseHoldings, SAMPLE_PORTFOLIO } from "@/lib/holdings";
import { num, pct } from "@/lib/format";

export default function RiskPage() {
  const [text, setText] = useState(SAMPLE_PORTFOLIO);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      setRes(await analyzeRisk(parseHoldings(text)));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Risk Command Center" />

      <Panel title="Portfolio (SYMBOL, weight)">
        <div className="row">
          <textarea rows={6} style={{ flex: 1, minWidth: 320 }} value={text} onChange={(e) => setText(e.target.value)} />
          <button className="primary" onClick={run} disabled={busy}>{busy ? "COMPUTING…" : "COMPUTE RISK"}</button>
        </div>
      </Panel>

      {err && <Panel title="Error"><div className="mono-block">{err}</div></Panel>}

      {res && (
        <>
          <div className="grid cols-4">
            <Panel title="Gross Exposure"><Metric label="gross" value={num(res.gross_exposure)} /></Panel>
            <Panel title="Net Exposure"><Metric label="net" value={num(res.net_exposure)} /></Panel>
            <Panel title="Leverage"><Metric label="x" value={num(res.leverage)} cls={res.leverage > 1.5 ? "warn" : "pos"} /></Panel>
            <Panel title="Beta"><Metric label="beta" value={num(res.beta)} /></Panel>
            <Panel title="Ann. Volatility"><Metric label="vol" value={pct(res.annualized_volatility)} /></Panel>
            <Panel title="VaR 95% (1D)"><Metric label="var" value={pct(res.var_95_daily)} cls="neg" /></Panel>
            <Panel title="Largest Position"><Metric label={res.largest_position?.symbol ?? "—"} value={pct(res.largest_position?.weight)} /></Panel>
          </div>

          <div className="grid cols-2" style={{ marginTop: 14 }}>
            <Panel title="Stress Tests">
              <table>
                <thead><tr><th>Scenario</th><th>Market Shock</th><th>Est. Portfolio PnL</th></tr></thead>
                <tbody>
                  {Object.entries(res.stress_tests).map(([k, v]: any) => (
                    <tr key={k}>
                      <td>{k}</td>
                      <td className="neg">{pct(v.market_shock)}</td>
                      <td className="neg">{pct(v.estimated_portfolio_pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
            <Panel title="Sector Concentration">
              <table>
                <tbody>
                  {Object.entries(res.sector_concentration).map(([s, v]: any) => (
                    <tr key={s}><td>{s}</td><td style={{ textAlign: "right" }}>{pct(v)}</td></tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          </div>
          <p className="note">{res.note}</p>
        </>
      )}
    </>
  );
}

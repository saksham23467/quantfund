"use client";

import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { analyzePortfolio } from "@/lib/api";
import { parseHoldings, SAMPLE_PORTFOLIO } from "@/lib/holdings";
import { num, pct } from "@/lib/format";

export default function PortfolioPage() {
  const [text, setText] = useState(SAMPLE_PORTFOLIO);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      setRes(await analyzePortfolio(parseHoldings(text)));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Portfolio Analytics" />

      <div className="grid cols-2">
        <Panel title="Upload / Paste Portfolio (SYMBOL, weight)">
          <textarea rows={11} style={{ width: "100%" }} value={text} onChange={(e) => setText(e.target.value)} />
          <div style={{ marginTop: 8 }}>
            <button className="primary" onClick={run} disabled={busy}>{busy ? "ANALYZING…" : "ANALYZE"}</button>
          </div>
        </Panel>

        <Panel title="Summary">
          {!res && <div className="note">Run an analysis to see results.</div>}
          {res && (
            <div className="grid cols-2">
              <Metric label="Beta (vs proxy)" value={num(res.beta_vs_market_proxy)} />
              <Metric label="VaR 95% (1D)" value={pct(res.var_95_daily)} cls="neg" />
              <Metric label="VaR 99% (1D)" value={pct(res.var_99_daily)} cls="neg" />
              <Metric label="Max Drawdown" value={pct(res.max_drawdown)} cls="neg" />
              <Metric label="Concentration (HHI)" value={num(res.concentration_hhi, 3)} />
            </div>
          )}
        </Panel>
      </div>

      {err && <Panel title="Error"><div className="mono-block">{err}</div></Panel>}

      {res && (
        <div className="grid cols-2" style={{ marginTop: 14 }}>
          <Panel title="Sector Exposure">
            <table>
              <tbody>
                {Object.entries(res.sector_exposure).map(([s, v]: any) => (
                  <tr key={s}>
                    <td>{s}</td>
                    <td style={{ width: 140 }}>
                      <div className="bar"><span style={{ width: `${Math.min(100, v * 100)}%` }} /></div>
                    </td>
                    <td style={{ textAlign: "right" }}>{pct(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          <Panel title="Top Holdings">
            <table>
              <tbody>
                {res.top_holdings.map((h: any) => (
                  <tr key={h.symbol}><td>{h.symbol}</td><td style={{ textAlign: "right" }}>{pct(h.weight)}</td></tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </div>
      )}

      {res && <p className="note">{res.note}</p>}
    </>
  );
}

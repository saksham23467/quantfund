"use client";

import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { studioAttribution, studioRiskDecomp, studioScenario } from "@/lib/api";
import { parseHoldings, SAMPLE_PORTFOLIO } from "@/lib/holdings";
import { num, pct } from "@/lib/format";

type Tab = "attribution" | "risk" | "scenario";

export default function StudioPage() {
  const [text, setText] = useState(SAMPLE_PORTFOLIO);
  const [tab, setTab] = useState<Tab>("attribution");
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(t: Tab) {
    setTab(t);
    setBusy(true);
    setErr(null);
    const holdings = parseHoldings(text);
    try {
      if (t === "attribution") setRes(await studioAttribution(holdings));
      else if (t === "risk") setRes(await studioRiskDecomp(holdings));
      else setRes(await studioScenario(holdings));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Portfolio Analytics Studio" />

      <Panel title="Portfolio (SYMBOL, weight)">
        <div className="row">
          <textarea rows={6} style={{ flex: 1, minWidth: 320 }} value={text} onChange={(e) => setText(e.target.value)} />
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <button className={tab === "attribution" ? "primary" : ""} onClick={() => run("attribution")} disabled={busy}>Factor Attribution</button>
            <button className={tab === "risk" ? "primary" : ""} onClick={() => run("risk")} disabled={busy}>Risk Decomposition</button>
            <button className={tab === "scenario" ? "primary" : ""} onClick={() => run("scenario")} disabled={busy}>Scenario Analysis</button>
          </div>
        </div>
      </Panel>

      {err && <Panel title="Error"><div className="mono-block">{err}</div></Panel>}

      {res && tab === "attribution" && (
        <Panel title="Factor Attribution">
          <div className="grid cols-3">
            <Metric label="Portfolio Return (ann.)" value={pct(res.portfolio_return_annualized)} />
            <Metric label="Factor Contribution" value={pct(res.factor_contribution_total)} />
            <Metric label="Specific Return" value={pct(res.specific_return)} />
          </div>
          <table>
            <thead><tr><th>Factor</th><th>Type</th><th>Exposure</th><th>Factor Ret (ann.)</th><th>Contribution</th></tr></thead>
            <tbody>
              {res.contributions.map((c: any) => (
                <tr key={c.factor}>
                  <td>{c.factor}</td>
                  <td className="muted">{c.is_proxy ? "proxy" : "price-based"}</td>
                  <td className={c.exposure >= 0 ? "pos" : "neg"}>{num(c.exposure)}</td>
                  <td>{pct(c.factor_return_annualized)}</td>
                  <td className={c.contribution_annualized >= 0 ? "pos" : "neg"}>{pct(c.contribution_annualized)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note">{res.note}</p>
        </Panel>
      )}

      {res && tab === "risk" && (
        <Panel title="Risk Decomposition">
          <div className="grid cols-2">
            <Metric label="Portfolio Vol (ann.)" value={pct(res.portfolio_volatility_annualized)} />
            <Metric label="Diversification Ratio" value={num(res.diversification_ratio)} />
          </div>
          <table>
            <thead><tr><th>Symbol</th><th>Weight</th><th>Marginal Risk</th><th>Component Risk</th><th>% of Total</th></tr></thead>
            <tbody>
              {res.contributions.map((c: any) => (
                <tr key={c.symbol}>
                  <td>{c.symbol}</td>
                  <td>{pct(c.weight)}</td>
                  <td>{num(c.marginal_risk, 4)}</td>
                  <td>{num(c.component_risk, 4)}</td>
                  <td>
                    <div className="bar"><span style={{ width: `${Math.min(100, c.pct_of_total_risk * 100)}%` }} /></div>
                    {pct(c.pct_of_total_risk)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note">{res.note}</p>
        </Panel>
      )}

      {res && tab === "scenario" && (
        <Panel title="Scenario Analysis">
          <div className="grid cols-2">
            <Metric label="Portfolio Beta" value={num(res.portfolio_beta)} />
            <Metric label="Worst Historical 5D" value={pct(res.historical_worst_5d?.return)} cls="neg" />
          </div>
          <table>
            <thead><tr><th>Scenario</th><th>Shocks</th><th>Estimated PnL</th></tr></thead>
            <tbody>
              {res.scenarios.map((s: any) => (
                <tr key={s.scenario}>
                  <td>{s.scenario}</td>
                  <td className="muted"><code>{JSON.stringify(s.shocks)}</code></td>
                  <td className={s.estimated_pnl >= 0 ? "pos" : "neg"}>{pct(s.estimated_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note">{res.note}</p>
        </Panel>
      )}
    </>
  );
}

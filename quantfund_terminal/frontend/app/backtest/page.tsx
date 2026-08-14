"use client";

import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, Metric } from "@/components/Panel";
import { Sparkline } from "@/components/Sparkline";
import { VerdictBadge } from "@/components/Badges";
import { runBacktest } from "@/lib/api";
import { num, pct } from "@/lib/format";

const FAMILIES = ["momentum", "trend", "mean_reversion", "breakout", "volatility"];

export default function BacktestPage() {
  const [form, setForm] = useState({
    family: "momentum",
    universe: "DEMO_NIFTY20",
    start: "2016-01-01",
    end: "2026-06-30",
    lookback: 126,
    holding_top_n: 5,
    rebalance_days: 21,
    cost_bps: 10,
    slippage_bps: 5,
  });
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const upd = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      setRes(await runBacktest(form));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  const s = res?.summary;
  return (
    <>
      <PageHeader title="Backtest Engine" />

      <Panel title="Configuration">
        <div className="row">
          <Field label="Family">
            <select value={form.family} onChange={(e) => upd("family", e.target.value)}>
              {FAMILIES.map((f) => <option key={f}>{f}</option>)}
            </select>
          </Field>
          <Field label="Universe"><input value={form.universe} onChange={(e) => upd("universe", e.target.value)} /></Field>
          <Field label="Start"><input value={form.start} onChange={(e) => upd("start", e.target.value)} /></Field>
          <Field label="End"><input value={form.end} onChange={(e) => upd("end", e.target.value)} /></Field>
          <Field label="Lookback"><input type="number" value={form.lookback} onChange={(e) => upd("lookback", +e.target.value)} /></Field>
          <Field label="Top N"><input type="number" value={form.holding_top_n} onChange={(e) => upd("holding_top_n", +e.target.value)} /></Field>
          <Field label="Rebalance (d)"><input type="number" value={form.rebalance_days} onChange={(e) => upd("rebalance_days", +e.target.value)} /></Field>
          <Field label="Cost (bps)"><input type="number" value={form.cost_bps} onChange={(e) => upd("cost_bps", +e.target.value)} /></Field>
          <Field label="Slippage (bps)"><input type="number" value={form.slippage_bps} onChange={(e) => upd("slippage_bps", +e.target.value)} /></Field>
          <Field label="&nbsp;"><button className="primary" onClick={run} disabled={busy}>{busy ? "RUNNING…" : "RUN BACKTEST"}</button></Field>
        </div>
      </Panel>

      {err && <Panel title="Error"><div className="mono-block">{err}</div></Panel>}

      {res && (
        <>
          <Panel
            title="Institutional Report"
            right={<VerdictBadge verdict={res.certification?.verdict} />}
          >
            <div className="grid cols-4">
              <Metric label="CAGR" value={pct(s.cagr)} cls={s.cagr >= 0 ? "pos" : "neg"} />
              <Metric label="Sharpe" value={num(s.sharpe)} />
              <Metric label="Sortino" value={num(s.sortino)} />
              <Metric label="Max Drawdown" value={pct(s.max_drawdown)} cls="neg" />
              <Metric label="Win Rate" value={pct(s.win_rate)} />
              <Metric label="Profit Factor" value={num(s.profit_factor)} />
              <Metric label="Turnover" value={num(s.turnover)} />
              <Metric label="Exposure" value={num(s.exposure)} />
            </div>
            <div style={{ marginTop: 8, color: "var(--warn)", fontSize: 11 }}>
              {res.certification?.banner}
            </div>
          </Panel>

          <Panel title="Equity Curve">
            <Sparkline data={res.equity_curve.map((p: any) => p.equity)} />
          </Panel>
          <Panel title="Drawdown">
            <Sparkline data={res.drawdown_curve.map((p: any) => p.drawdown)} color="#ff5c5c" />
          </Panel>
        </>
      )}
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <label dangerouslySetInnerHTML={{ __html: label }} />
      {children}
    </div>
  );
}

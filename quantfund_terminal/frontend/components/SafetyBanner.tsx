"use client";

import { useEffect, useState } from "react";
import { getSafety } from "@/lib/api";

export function SafetyBanner() {
  const [s, setS] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getSafety().then(setS).catch((e) => setErr(String(e)));
  }, []);

  if (err)
    return (
      <div className="safety-banner" style={{ color: "var(--warn)", borderColor: "var(--warn)" }}>
        Gateway offline — start the backend on :8000 (see README).
      </div>
    );
  if (!s) return <div className="safety-banner">Loading safety state…</div>;

  return (
    <div className="safety-banner">
      <span>Live: <b>{s.live_trading}</b></span>
      <span>Paper: <b>{s.paper_trading}</b></span>
      <span>Broker write: <b>{s.broker_write_capability}</b></span>
      <span>Kill switch: <b>{s.kill_switch}</b></span>
      <span>Mode: <b>{s.product_mode}</b></span>
    </div>
  );
}

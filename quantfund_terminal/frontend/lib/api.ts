// Typed client for the QuantFund Research Terminal gateway.
import { personaHeaders } from "./persona";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function api<T = any>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...personaHeaders(),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed (${res.status}): ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export const getHealth = () => api("/health");
export const getSafety = () => api("/api/safety");
export const getMarket = () => api("/api/market");
export const getCertification = () => api("/api/certification");
export const getLeaderboard = () => api("/api/leaderboard");
export const getAudit = () => api("/api/audit");
export const getFactors = (lookback = 126) =>
  api(`/api/factors?lookback=${lookback}`);
export const listStrategies = () => api("/api/strategies");

export const createStrategy = (body: {
  name: string;
  family: string;
  params?: Record<string, unknown>;
}) => api("/api/strategies", { method: "POST", body: JSON.stringify(body) });

export const runBacktest = (body: Record<string, unknown>) =>
  api("/api/backtest", { method: "POST", body: JSON.stringify(body) });

export const analyzePortfolio = (holdings: unknown[]) =>
  api("/api/portfolio", { method: "POST", body: JSON.stringify({ holdings }) });

export const analyzeRisk = (holdings: unknown[]) =>
  api("/api/risk", { method: "POST", body: JSON.stringify({ holdings }) });

export const askCopilot = (prompt: string) =>
  api("/api/copilot", { method: "POST", body: JSON.stringify({ prompt }) });

// --- v2 (multi-tenant SaaS) -------------------------------------------------
export const getMe = () => api("/api/v2/me");
export const getDatasets = () => api("/api/v2/datasets");
export const getMarketplace = () => api("/api/v2/marketplace");
export const getProof = (id: number) => api(`/api/v2/marketplace/${id}/proof`);
export const getInvestor = () => api("/api/v2/investor");
export const getAuditRecords = () => api("/api/v2/audit/records");
export const verifyChain = () => api("/api/v2/audit/verify");

export const studioAttribution = (holdings: unknown[]) =>
  api("/api/v2/studio/attribution", { method: "POST", body: JSON.stringify({ holdings }) });
export const studioRiskDecomp = (holdings: unknown[]) =>
  api("/api/v2/studio/risk-decomposition", { method: "POST", body: JSON.stringify({ holdings }) });
export const studioScenario = (holdings: unknown[]) =>
  api("/api/v2/studio/scenario", { method: "POST", body: JSON.stringify({ holdings }) });

export const publishStrategy = (body: {
  name: string;
  family: string;
  params?: Record<string, unknown>;
}) => api("/api/v2/marketplace/publish", { method: "POST", body: JSON.stringify(body) });

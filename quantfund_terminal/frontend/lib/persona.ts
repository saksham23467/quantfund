// Demo persona = (org, user, role). Persisted in localStorage and sent as
// tenant headers on every API call. In production these come from an OIDC/JWT.
export type Persona = { orgSlug: string; email: string; role: string; label: string };

export const PERSONAS: Persona[] = [
  { label: "Demo Capital · Admin", orgSlug: "demo-capital", email: "admin@demo-capital.in", role: "admin" },
  { label: "Demo Capital · PM", orgSlug: "demo-capital", email: "pm@demo-capital.in", role: "pm" },
  { label: "Demo Capital · Analyst", orgSlug: "demo-capital", email: "analyst@demo-capital.in", role: "analyst" },
  { label: "Demo Capital · Viewer", orgSlug: "demo-capital", email: "viewer@demo-capital.in", role: "viewer" },
  { label: "Alpha Quant AMC · Admin", orgSlug: "alpha-quant", email: "admin@alpha-quant.in", role: "admin" },
  { label: "Solo Analyst", orgSlug: "solo-analyst", email: "analyst@solo-analyst.in", role: "analyst" },
];

const KEY = "qft_persona";

export function getPersona(): Persona {
  if (typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(KEY);
      if (raw) return JSON.parse(raw) as Persona;
    } catch {
      /* ignore */
    }
  }
  return PERSONAS[0];
}

export function setPersona(p: Persona): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(KEY, JSON.stringify(p));
    window.dispatchEvent(new Event("qft-persona-changed"));
  }
}

export function personaHeaders(): Record<string, string> {
  const p = getPersona();
  return { "X-Org-Slug": p.orgSlug, "X-User-Email": p.email, "X-Role": p.role };
}

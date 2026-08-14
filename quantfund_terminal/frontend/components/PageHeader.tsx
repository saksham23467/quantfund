import { ReactNode } from "react";
import { SafetyBanner } from "./SafetyBanner";

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="topbar">
      <h1>{title}</h1>
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        {children}
        <SafetyBanner />
      </div>
    </div>
  );
}

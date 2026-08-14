import { ReactNode } from "react";

export function Panel({
  title,
  children,
  right,
}: {
  title?: string;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="panel">
      {(title || right) && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          {title && <h3>{title}</h3>}
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

export function Metric({
  label,
  value,
  cls,
}: {
  label: string;
  value: ReactNode;
  cls?: string;
}) {
  return (
    <div className="metric">
      <span className="label">{label}</span>
      <span className={`value ${cls ?? ""}`}>{value}</span>
    </div>
  );
}

import { PageHeader } from "./PageHeader";
import { Panel } from "./Panel";

export function Loading({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <Panel>
        <div className="note">Loading…</div>
      </Panel>
    </>
  );
}

export function Offline({ title, err }: { title: string; err: string }) {
  return (
    <>
      <PageHeader title={title} />
      <Panel title="Gateway offline">
        <div className="note">
          Could not reach the API. Start the backend:{" "}
          <code>quantfund_terminal/backend/run.sh</code>
          <div className="mono-block" style={{ marginTop: 8 }}>
            {err}
          </div>
        </div>
      </Panel>
    </>
  );
}

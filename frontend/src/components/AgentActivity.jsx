import { AGENT_LABELS, fmtDateTime, normaliseActivity, statusTone } from "../lib/format.js";

export default function AgentActivity({ activity = [], analysis }) {
  const events = activity.map(normaliseActivity);
  const toolCalls = analysis?.metrics?.tool_calls;

  return (
    <section className="card overview-card" aria-labelledby="activity-title">
      <div className="card-header">
        <div>
          <h2 id="activity-title">AI processing centre</h2>
          <p>Live agent events recorded by the orchestrator</p>
        </div>
        <span className={`pill ${statusTone(analysis?.status ?? "QUEUED")}`}>
          {analysis?.status ?? "NOT_STARTED"}
        </span>
      </div>

      <div className="row-between muted small">
        <span>Current agent: {analysis?.current_agent ?? "—"}</span>
        <span>Engine: {analysis?.engine ?? "deterministic"}</span>
        <span>Tool calls: {toolCalls ?? "n/a"}</span>
      </div>

      {events.length === 0 ? (
        <p className="empty-state">
          No agent activity recorded yet. Upload documents and start an analysis to watch the
          orchestrator and its five specialists work.
        </p>
      ) : (
        <ul className="activity-list">
          {events.map((event) => (
            <li className="activity-row" key={event.id}>
              <span className={`activity-dot ${statusTone(event.status)}`} aria-hidden="true" />
              <div className="activity-body">
                <div className="row-between">
                  <strong>{AGENT_LABELS[event.agent] ?? event.agent}</strong>
                  <span className={`pill ${statusTone(event.status)}`}>{event.status}</span>
                </div>
                <p>{event.message || event.type}</p>
                <span className="muted small">{fmtDateTime(event.timestamp)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

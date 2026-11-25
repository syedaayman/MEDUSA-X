import { fmtDateTime, initials, statusTone } from "../lib/format.js";

export default function PatientOverview({ patient, counts = {}, analysis, onRun, isRunning, error }) {
  const name = patient?.display_name || patient?.id || "Patient";
  const status = analysis?.status ?? "NOT_STARTED";
  const initialsLabel = patient?.id?.startsWith("DEMO-")
    ? `P${patient.id.replace("DEMO-", "")}`
    : initials(name);
  const isSynthetic = patient?.id?.startsWith("sample-") || patient?.id?.startsWith("DEMO-");

  return (
    <section className="card patient-card">
      <div className="card-header">
        <div className="patient-profile">
          <div className="avatar" aria-hidden="true">{initialsLabel}</div>
          <div>
            <p className="eyebrow">Patient overview</p>
            <h2>{name}</h2>
            <p className="muted small">
              {patient?.id ?? "unknown patient"}
              {patient?.data_origin ? ` · ${patient.data_origin}` : ""}
              {patient?.updated_at ? ` · updated ${fmtDateTime(patient.updated_at)}` : ""}
              {isSynthetic ? " · Synthetic Dataset" : ""}
            </p>
          </div>
        </div>
        <span className={`pill ${statusTone(status)}`}>{status}</span>
      </div>

      <div className="patient-stats">
        <div><span className="stat-label">Documents</span><span className="stat-value">{counts.documents ?? 0}</span></div>
        <div><span className="stat-label">Clinical entities</span><span className="stat-value">{counts.entities ?? 0}</span></div>
        <div><span className="stat-label">Timeline events</span><span className="stat-value">{counts.events ?? 0}</span></div>
        <div><span className="stat-label">Potential conflicts</span><span className="stat-value">{counts.conflicts ?? 0}</span></div>
        <div><span className="stat-label">Needs review</span><span className="stat-value">{counts.pending ?? 0}</span></div>
        <div><span className="stat-label">Engine</span><span className="stat-value">{analysis?.engine ?? "—"}</span></div>
      </div>

      <div className="row-between top-gap">
        <span className="muted small">
          {analysis?.completed_at
            ? `Last run completed ${fmtDateTime(analysis.completed_at)}`
            : analysis?.started_at
              ? `Run started ${fmtDateTime(analysis.started_at)}`
              : "No analysis run yet"}
        </span>
        <button className="button" disabled={isRunning || !counts.documents} onClick={onRun} type="button">
          {isRunning ? "Analysis running…" : "Run agent analysis"}
        </button>
      </div>

      {analysis?.error_message && <p className="notice error">{analysis.error_message}</p>}
      {Array.isArray(analysis?.warnings) && analysis.warnings.length > 0 && (
        <div className="notice">
          <strong>Quality warnings</strong>
          <ul className="plain-list">
            {analysis.warnings.slice(0, 6).map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      {error && <p className="notice error">{error}</p>}
    </section>
  );
}

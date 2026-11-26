import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import FileUpload from "../components/FileUpload.jsx";
import { apiError, listPatients } from "../services/api.js";
import { asList, fmtDateTime, statusTone } from "../lib/format.js";

export default function Dashboard() {
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listPatients();
      setPatients(asList(data, "patients"));
      setError("");
    } catch (loadError) {
      setError(apiError(loadError, "Could not load patients. Is the API running?"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const totals = patients.reduce(
    (acc, p) => ({
      patients: acc.patients + 1,
      documents: acc.documents + (p.document_count ?? 0),
      entities: acc.entities + (p.entity_count ?? 0),
      conflicts: acc.conflicts + (p.pending_review_count ?? 0),
    }),
    { patients: 0, documents: 0, entities: 0, conflicts: 0 },
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>Record overview</h1>
          <p className="page-subtitle">
            Upload patient documents, run the agent team, and review evidence-backed findings.
          </p>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Total patients</span>
          <span className="stat-value">{loading ? "—" : totals.patients}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Documents processed</span>
          <span className="stat-value">{loading ? "—" : totals.documents}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Clinical entities</span>
          <span className="stat-value">{loading ? "—" : totals.entities}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Conflicts awaiting review</span>
          <span className="stat-value">{loading ? "—" : totals.conflicts}</span>
        </div>
      </div>

      {error && <p className="notice error">{error}</p>}

      <div className="dashboard-grid">
        <div className="stack">
          <section className="card overview-card" aria-labelledby="patients-title">
            <div className="card-header">
              <div>
                <h2 id="patients-title">Recent patients</h2>
                <p>Uploaded clinical records only · dataset patients are listed separately</p>
              </div>
              <button className="button button-secondary" onClick={load} type="button">
                Refresh
              </button>
            </div>

            {loading && <p className="empty-state">Loading patients…</p>}
            {!loading && !error && patients.length === 0 && (
              <p className="empty-state">
                No patient records yet. Upload one or more PDFs on the right to create the first
                patient workspace.
              </p>
            )}

            <div className="patient-list">
              {patients.map((patient) => (
                <Link className="patient-row" key={patient.id} to={`/patients/${encodeURIComponent(patient.id)}`}>
                  <div>
                    <strong>{patient.display_name ?? patient.id}</strong>
                    <p className="muted small">
                      {patient.id} · updated {fmtDateTime(patient.updated_at ?? patient.created_at)}
                    </p>
                  </div>
                  <div className="tag-row">
                    <span className="tag">{patient.document_count ?? 0} docs</span>
                    <span className="tag">{patient.entity_count ?? 0} entities</span>
                    <span className={`pill ${statusTone(patient.pending_review_count ? "PENDING" : "COMPLETED")}`}>
                      {patient.pending_review_count ?? 0} to review
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        </div>

        <div className="stack">
          <FileUpload onUploaded={load} />
          <section className="card overview-card" aria-labelledby="quick-actions-title">
            <div className="card-header">
              <div>
                <h2 id="quick-actions-title">Quick actions</h2>
                <p>Common workflows</p>
              </div>
            </div>
            <div className="tag-row">
              <Link className="button" to="/dashboard">Browse patients</Link>
              <Link className="button button-secondary" to="/">How it works</Link>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

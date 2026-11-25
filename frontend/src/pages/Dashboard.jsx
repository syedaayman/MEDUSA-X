import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import DatasetPanel from "../components/DatasetPanel.jsx";
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
        <span className="demo-badge">Decision-support prototype</span>
      </div>

      <div className="dashboard-grid">
        <div className="stack">
          <section className="card overview-card" aria-labelledby="patients-title">
            <div className="card-header">
              <div>
                <h2 id="patients-title">Patients</h2>
                <p>Uploaded clinical records only · dataset patients are listed separately</p>
              </div>
              <button className="button button-secondary" onClick={load} type="button">
                Refresh
              </button>
            </div>

            {loading && <p className="empty-state">Loading patients…</p>}
            {error && <p className="notice error">{error}</p>}

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

          <DatasetPanel />
        </div>

        <div className="stack">
          <FileUpload onUploaded={load} />
        </div>
      </div>
    </>
  );
}

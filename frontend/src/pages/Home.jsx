import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiError, loadSampleCase } from "../services/api.js";
import FileUpload from "../components/FileUpload.jsx";

const features = [
  {
    icon: "↗",
    title: "Reconstruct a timeline",
    description:
      "Bring discharge summaries, prescriptions and reports into one chronological, source-linked record.",
  },
  {
    icon: "◇",
    title: "Surface discrepancies",
    description:
      "Compare medications, diagnoses, allergies and laboratory values across documents — and reject the findings that do not hold up.",
  },
  {
    icon: "◎",
    title: "Keep evidence in view",
    description:
      "Every entity, event and finding cites the document and page it came from, with the original page text one click away.",
  },
];

const SAMPLES = [
  {
    id: "DEMO-001",
    title: "Patient 1 — Diabetes, Hypertension, Dyslipidemia",
    description: "Longitudinal history with conflicting Metformin doses, medication status uncertainty, lab trends and vitals.",
    types: "Consultation, Laboratory Report, Prescription, Discharge Summary",
  },
  {
    id: "DEMO-002",
    title: "Patient 2 — Coronary Artery Disease",
    description: "CAD history with medication status conflicts, allergy documentation conflict and lipid trends.",
    types: "Consultation, Diagnostic Report, Follow-up, Specialist Assessment",
  },
  {
    id: "DEMO-003",
    title: "Patient 3 — Asthma, Hypothyroidism, Allergic Rhinitis",
    description: "Respiratory and thyroid history with levothyroxine dose mismatch and inhaler documentation differences.",
    types: "Consultation, Laboratory Report, Follow-up, Specialist Assessment",
  },
];

export default function Home() {
  const navigate = useNavigate();
  const [loadingSample, setLoadingSample] = useState("");
  const [sampleError, setSampleError] = useState("");

  async function handleLoadSample(id) {
    setLoadingSample(id);
    setSampleError("");
    try {
      const result = await loadSampleCase(id);
      navigate(`/patients/${encodeURIComponent(result.patient_id)}`);
    } catch (err) {
      setSampleError(apiError(err, "Could not load the sample case."));
    } finally {
      setLoadingSample("");
    }
  }

  return (
    <>
      <section className="hero-card">
        <div className="hero-content">
          <p className="eyebrow">Clinical record reconciliation</p>
          <h1>Orchestrator + five specialist stages. One traceable clinical record.</h1>
          <p>
            MEDUSA-X is a decision-support prototype that reads fragmented clinical documents,
            structures the facts, reconciles them across records, verifies each potential
            discrepancy against the original page, and builds an evidence-backed history. It never
            diagnoses, prescribes or decides which record is correct.
          </p>
          <Link className="button" to="/dashboard">
            Open the workspace
          </Link>
        </div>
      </section>

      <section className="card overview-card" aria-labelledby="samples-title">
        <div className="card-header">
          <div>
            <h2 id="samples-title">Recent cases</h2>
            <p>De-identified longitudinal records ready for clinical reconciliation</p>
          </div>
        </div>
        {sampleError && <p className="notice error">{sampleError}</p>}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-stretch">
          {SAMPLES.map((sample) => (
            <article className="doc-card flex flex-col" key={sample.id}>
              <div className="flex-1">
                <strong className="block">{sample.title}</strong>
                <p className="muted small">{sample.description}</p>
                <p className="muted small">Documents: {sample.types}</p>
              </div>
              <button
                className="button button-secondary w-full mt-3"
                disabled={loadingSample === sample.id}
                onClick={() => handleLoadSample(sample.id)}
                type="button"
              >
                {loadingSample === sample.id ? "Loading…" : "Open case"}
              </button>
            </article>
          ))}
        </div>
      </section>

      <div className="dashboard-grid top-gap">
        <FileUpload />
        <aside className="card overview-card">
          <div className="card-header">
            <div>
              <h2>Agent team</h2>
              <p>Orchestrator plus five specialists</p>
            </div>
            <span className="pill idle">Agents SDK</span>
          </div>
          <ul className="plain-list">
            <li>
              <strong>Orchestrator</strong> — decides which specialists run, retries bounded failures and
              refuses to continue when extraction fails.
            </li>
            <li>
              <strong>Document Intelligence</strong> — classifies each document, finds the clinical date
              and flags pages that need OCR.
            </li>
            <li>
              <strong>Clinical Structuring</strong> — extracts entities with original wording, page and
              snippet.
            </li>
            <li>
              <strong>Reconciliation</strong> — compares comparable records only, and distinguishes
              change over time from inconsistency.
            </li>
            <li>
              <strong>Evidence Verification</strong> — re-reads the original pages and can reject a
              proposed conflict.
            </li>
            <li>
              <strong>Timeline &amp; Summary</strong> — orders events and writes a cited summary.
            </li>
          </ul>
          <p className="notice">
            Prototype notice: synthetic and uploaded demonstration data only. Not a medical device,
            not compliant with healthcare regulation, and never a substitute for clinician review.
          </p>
        </aside>
      </div>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4 items-stretch top-gap" aria-label="Project capabilities">
        {features.map((feature) => (
          <article className="card feature-card" key={feature.title}>
            <span className="feature-icon" aria-hidden="true">
              {feature.icon}
            </span>
            <h2>{feature.title}</h2>
            <p>{feature.description}</p>
          </article>
        ))}
      </section>
    </>
  );
}

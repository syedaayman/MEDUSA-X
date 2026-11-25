import { Link } from "react-router-dom";
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

export default function Home() {
  return (
    <>
      <section className="hero-card">
        <div className="hero-content">
          <p className="eyebrow">Clinical record reconciliation</p>
          <h1>Six agents. One traceable clinical record.</h1>
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

      <section className="feature-grid" aria-label="Project capabilities">
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
    </>
  );
}

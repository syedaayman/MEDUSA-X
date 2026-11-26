import { useState } from "react";
import { fmtDate } from "../lib/format.js";

function SectionList({ items }) {
  if (!Array.isArray(items) || items.length === 0) {
    return <p className="muted small">Not documented.</p>;
  }
  return (
    <ul className="plain-list">
      {items.map((item, index) => (
        <li key={index}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
      ))}
    </ul>
  );
}

function renderChange(change) {
  if (!change || typeof change !== "object") return String(change);
  const sequence = Array.isArray(change.sequence) ? change.sequence : [];
  return (
    <li key={change.subject ?? JSON.stringify(change)}>
      <strong>{change.subject ?? "Medication"}</strong>
      {sequence.length > 0 && (
        <ul className="plain-list">
          {sequence.map((step, i) => (
            <li key={i}>{step.date ? `${step.date}: ` : ""}{step.description}</li>
          ))}
        </ul>
      )}
      {change.note && <p className="muted small">{change.note}</p>}
    </li>
  );
}

function renderDiscrepancy(d) {
  if (!d || typeof d !== "object") return String(d);
  return (
    <li key={d.id ?? JSON.stringify(d)}>
      <strong>{d.category ?? "Discrepancy"}</strong>
      {d.severity ? ` · ${d.severity}` : ""}
      {d.description ? <p>{d.description}</p> : null}
      <p className="muted small">
        {d.verification_status ? `Verification: ${d.verification_status}` : ""}
        {d.review_status ? ` · Review: ${d.review_status}` : ""}
      </p>
    </li>
  );
}

export default function SummaryPanel({ summary, loading, error }) {
  const [expanded, setExpanded] = useState(false);
  const sections = summary?.sections && typeof summary.sections === "object" ? summary.sections : {};
  const overview = sections.overview && typeof sections.overview === "object" ? sections.overview : null;
  const counts = sections.counts && typeof sections.counts === "object" ? sections.counts : null;

  // Merge any legacy "medications_status_unclear" items into historical_medications
  // so they display under the Historical medications heading instead of their own.
  if (Array.isArray(sections.medications_status_unclear) && sections.medications_status_unclear.length > 0) {
    sections.historical_medications = [
      ...(Array.isArray(sections.historical_medications) ? sections.historical_medications : []),
      ...sections.medications_status_unclear,
    ];
  }

  const readableSections = Object.entries(sections).filter(
    ([key]) => !["overview", "counts", "changes_over_time", "potential_discrepancies", "medications_status_unclear"].includes(key),
  );

  return (
    <section className="card summary-card" aria-labelledby="summary-title">
      <div className="card-header">
        <div>
          <h2 id="summary-title">Evidence-backed summary</h2>
          <p>{summary?.stored ? "Stored from the last analysis run" : "Generated from stored evidence"}</p>
        </div>
        <span className="pill idle">prototype</span>
      </div>

      {loading && <p className="empty-state">Loading patient summary…</p>}
      {error && <p className="notice error">{error}</p>}

      {!loading && !error && !summary && (
        <p className="empty-state">
          No summary yet. Upload documents and run an analysis; the Timeline &amp; Summary agent will
          write a summary strictly from stored, cited evidence.
        </p>
      )}

      {summary && (
        <>
          {summary.summary && (
            <div className="summary-section">
              <h3>Overview</h3>
              <p>{summary.summary}</p>
              {overview && (
                <p className="muted small">
                  {overview.document_count != null ? `${overview.document_count} document(s)` : ""}
                  {overview.entities != null ? ` · ${overview.entities} clinical item(s)` : ""}
                </p>
              )}
            </div>
          )}

          {readableSections.map(([key, value]) => (
            <div className="summary-section" key={key}>
              <h3>{key.replace(/_/g, " ")}</h3>
              <SectionList items={Array.isArray(value) ? value : [value]} />
            </div>
          ))}

          {Array.isArray(sections.changes_over_time) && sections.changes_over_time.length > 0 && (
            <div className="summary-section">
              <h3>Changes over time</h3>
              <ul className="plain-list">{sections.changes_over_time.map(renderChange)}</ul>
            </div>
          )}

          {Array.isArray(sections.potential_discrepancies) && sections.potential_discrepancies.length > 0 && (
            <div className="summary-section">
              <h3>Potential discrepancies</h3>
              <ul className="plain-list">{sections.potential_discrepancies.map(renderDiscrepancy)}</ul>
            </div>
          )}

          {counts && (
            <div className="summary-section">
              <h3>Counts</h3>
              <p className="muted small">
                {Object.entries(counts).map(([k, v]) => `${k}: ${v}`).join(" · ")}
              </p>
            </div>
          )}

          {Array.isArray(summary.uncertainty_notes) && summary.uncertainty_notes.length > 0 && (
            <div className="summary-section">
              <h3>Missing or uncertain information</h3>
              <ul className="plain-list">
                {summary.uncertainty_notes.map((note, index) => (
                  <li key={index}>{note}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      <div className="notice">
        Decision-support prototype. This summary is not a diagnosis, prescription or treatment
        recommendation, and it does not replace clinician review of the original documents.
      </div>
    </section>
  );
}

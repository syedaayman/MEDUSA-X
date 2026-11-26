import { useState } from "react";
import { fmtDate, statusTone } from "../lib/format.js";

const REVIEW_ACTIONS = [
  { value: "REVIEWED", label: "Mark reviewed" },
  { value: "UNRESOLVED", label: "Keep unresolved" },
  { value: "DISMISSED", label: "Dismiss as not a conflict" },
];

export default function ConflictPanel({ conflicts = [], onReview, onOpenEvidence, busyId }) {
  const [notes, setNotes] = useState({});

  return (
    <section className="card conflict-card" aria-labelledby="conflict-title">
      <div className="card-header">
        <div>
          <h2 id="conflict-title">Reconciliation review</h2>
          <p>Potential discrepancies only · never a confirmed clinical error</p>
        </div>
        <span className="pill warn">{conflicts.length} finding(s)</span>
      </div>

      {conflicts.length === 0 ? (
        <p className="empty-state">
          No potential discrepancies stored for this patient. A single document cannot produce
          cross-document conflicts, and legitimate changes over time are not flagged.
        </p>
      ) : (
        conflicts.map((conflict) => (
          <article className="conflict-item" key={conflict.conflict_id}>
            <div className="conflict-title">
              <span aria-hidden="true">!</span>
              {conflict.category} · {conflict.severity ?? "MEDIUM"}
            </div>
            <p>{conflict.description}</p>

            <div className="tag-row">
              <span className={`pill ${statusTone(conflict.verification_status)}`}>
                {conflict.verification_status ?? "UNVERIFIED"}
              </span>
              <span className={`pill ${statusTone(conflict.review_status)}`}>
                review: {conflict.review_status ?? "PENDING"}
              </span>
              {conflict.confidence != null && (
                <span className="tag">confidence {Number(conflict.confidence).toFixed(2)}</span>
              )}
            </div>

            {Array.isArray(conflict.compared_values) && conflict.compared_values.length > 0 && (
              <ul className="plain-list">
                {conflict.compared_values.map((value, index) => (
                  <li key={`${conflict.conflict_id}-value-${index}`}>
                    <strong>Value {index + 1}:</strong> {value}
                  </li>
                ))}
              </ul>
            )}

            {conflict.reason && <p className="muted small">Why flagged: {conflict.reason}</p>}
            {conflict.possible_explanation && (
              <p className="muted small">Possible explanation: {conflict.possible_explanation}</p>
            )}
            {conflict.verification_reason && (
              <p className="muted small">Verification: {conflict.verification_reason}</p>
            )}
            {conflict.reviewer_note && <p className="muted small">Reviewer note: {conflict.reviewer_note}</p>}

            {Array.isArray(conflict.source_references) && conflict.source_references.length > 0 && (
              <ul className="plain-list">
                {conflict.source_references.map((reference, index) => (
                  <li key={`${conflict.conflict_id}-ref-${index}`}>
                    <span className="tag">
                      {reference.document_name ?? reference.document_id ?? "document"}
                      {reference.page ? ` · p.${reference.page}` : ""}
                      {reference.clinical_date ? ` · ${fmtDate(reference.clinical_date)}` : ""}
                    </span>
                    {reference.snippet && <span className="muted small"> “{reference.snippet}”</span>}
                  </li>
                ))}
              </ul>
            )}

            <div className="row-between top-gap">
              <button
                className="link-button"
                onClick={() => onOpenEvidence?.({ kind: "conflict", id: conflict.conflict_id })}
                type="button"
              >
                Inspect original evidence
              </button>
              <span className="muted small">
                {conflict.requires_human_review ? "Human review required" : "Verified automatically"}
              </span>
            </div>

            <label className="field">
              <span className="field-label">Reviewer note</span>
              <input
                className="text-input"
                onChange={(event) =>
                  setNotes((current) => ({ ...current, [conflict.conflict_id]: event.target.value }))
                }
                placeholder="Optional note kept in the audit trail"
                value={notes[conflict.conflict_id] ?? ""}
              />
            </label>

            <div className="tag-row">
              {REVIEW_ACTIONS.map((action) => (
                <button
                  className="button button-secondary"
                  disabled={busyId === conflict.conflict_id}
                  key={action.value}
                  onClick={() => onReview?.(conflict.conflict_id, action.value, notes[conflict.conflict_id] ?? "")}
                  type="button"
                >
                  {action.label}
                </button>
              ))}
            </div>
          </article>
        ))
      )}
    </section>
  );
}

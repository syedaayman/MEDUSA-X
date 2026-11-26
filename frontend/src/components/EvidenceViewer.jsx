import { fmtDate } from "../lib/format.js";

export default function EvidenceViewer({ evidence, loading, error, onClose }) {
  if (!evidence && !loading && !error) return null;

  const references = evidence?.references ?? [];

  return (
    <section className="card evidence-card" aria-labelledby="evidence-title">
      <div className="card-header">
        <div>
          <h2 id="evidence-title">Evidence viewer</h2>
          <p>Original stored page text — nothing is reconstructed</p>
        </div>
        <button className="button button-secondary" onClick={onClose} type="button">
          Close
        </button>
      </div>

      {loading && <p className="empty-state">Loading original source text…</p>}
      {error && <p className="notice error">{error}</p>}

      {evidence && (
        <>
          {evidence.description && <p className="muted small">{evidence.description}</p>}
          {evidence.verification_status && (
            <p className="muted small">Verification decision: {evidence.verification_status}</p>
          )}

          {references.length === 0 && (
            <article className="evidence-row">
              <div className="evidence-meta">
                <strong>{evidence.filename ?? "Source document"}</strong>
                <span>{evidence.page ? `Page ${evidence.page}` : "Page unknown"}</span>
              </div>
              {evidence.event_date && <p className="muted small">Event date: {fmtDate(evidence.event_date)}</p>}
              {evidence.snippet && <p className="evidence-quote">“{evidence.snippet}”</p>}
              {evidence.page_text ? (
                <pre className="extracted-page">{evidence.page_text}</pre>
              ) : (
                <p className="empty-state">
                  {evidence.ocr_required
                    ? "This page has no extractable text and was marked OCR_REQUIRED."
                    : "No page text is available for this reference."}
                </p>
              )}
            </article>
          )}

          {references.map((reference) => (
            <article className="evidence-row" key={reference.entity_id}>
              <div className="evidence-meta">
                <strong>
                  {reference.filename ?? reference.document_id ?? "document"} · {reference.category ?? "entity"}
                </strong>
                <span>{reference.page ? `Page ${reference.page}` : "Page unknown"}</span>
              </div>
              {reference.available === false ? (
                <p className="notice error">{reference.reason ?? "Evidence unavailable."}</p>
              ) : (
                <>
                  <p className="muted small">
                    Extracted value: <strong>{reference.value ?? "—"}</strong>
                    {reference.original_value && reference.original_value !== reference.value
                      ? ` (original wording: “${reference.original_value}”)`
                      : ""}
                    {reference.clinical_date ? ` · ${fmtDate(reference.clinical_date)}` : ""}
                  </p>
                  {reference.snippet && <p className="evidence-quote">“{reference.snippet}”</p>}
                  {reference.page_text ? (
                    <pre className="extracted-page">{reference.page_text}</pre>
                  ) : (
                    <p className="empty-state">
                      {reference.ocr_required
                        ? "This page has no extractable text and was marked OCR_REQUIRED."
                        : "No page text stored for this reference."}
                    </p>
                  )}
                </>
              )}
            </article>
          ))}
        </>
      )}
    </section>
  );
}

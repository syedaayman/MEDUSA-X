function renderSectionValue(value) {
  if (value == null) return <p className="muted small">Not documented.</p>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <p className="muted small">None documented.</p>;
    return (
      <ul className="plain-list">
        {value.map((item, index) => (
          <li key={index}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") return <p className="muted small">{JSON.stringify(value)}</p>;
  return <p>{String(value)}</p>;
}

export default function SummaryPanel({ summary, loading, error }) {
  const sections = summary?.sections && typeof summary.sections === "object" ? summary.sections : {};
  const sectionEntries = Object.entries(sections);

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
            </div>
          )}

          {sectionEntries.map(([key, value]) => (
            <div className="summary-section" key={key}>
              <h3>{key.replace(/_/g, " ")}</h3>
              {renderSectionValue(value)}
            </div>
          ))}

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

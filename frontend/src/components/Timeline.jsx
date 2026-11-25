import { useMemo, useState } from "react";
import { fmtDate, statusTone } from "../lib/format.js";

const CATEGORY_FILTERS = ["ALL", "DIAGNOSIS", "MEDICATION", "ALLERGY", "LAB_RESULT", "PROCEDURE", "VITAL_SIGN", "SYMPTOM", "PLAN"];

export default function Timeline({ events = [], onOpenEvidence }) {
  const [filter, setFilter] = useState("ALL");

  const visible = useMemo(() => {
    const list = filter === "ALL" ? events : events.filter((event) => String(event.category).toUpperCase() === filter);
    return [...list].sort((a, b) => String(a.event_date ?? "9999").localeCompare(String(b.event_date ?? "9999")));
  }, [events, filter]);

  return (
    <section className="card timeline-card" aria-labelledby="timeline-title">
      <div className="card-header">
        <div>
          <h2 id="timeline-title">Clinical timeline</h2>
          <p>{events.length} event(s) reconstructed from stored evidence</p>
        </div>
        <span className="pill idle">chronological</span>
      </div>

      <div className="filter-row">
        {CATEGORY_FILTERS.map((category) => (
          <button
            className={`chip${filter === category ? " active" : ""}`}
            key={category}
            onClick={() => setFilter(category)}
            type="button"
          >
            {category.toLowerCase()}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="empty-state">
          {events.length === 0
            ? "No timeline events yet. Events appear after a document analysis run completes."
            : "No events match this filter."}
        </p>
      ) : (
        <div className="timeline-list">
          {visible.map((event) => (
            <article className="timeline-item" key={event.event_id}>
              <time className="timeline-date" dateTime={event.event_date ?? undefined}>
                {fmtDate(event.event_date)}
                {event.date_precision && event.date_precision !== "DAY" ? (
                  <span className="muted small"> · {event.date_precision.toLowerCase()}</span>
                ) : null}
              </time>
              <div className="timeline-content">
                <span className="timeline-marker" aria-hidden="true" />
                <strong>{event.category}</strong>
                <p>{event.description}</p>
                <div className="tag-row">
                  <span className={`pill ${statusTone(event.verification_status)}`}>
                    {event.verification_status ?? "UNVERIFIED"}
                  </span>
                  {event.source_document_name && (
                    <span className="tag">
                      {event.source_document_name}
                      {event.source_page ? ` · p.${event.source_page}` : ""}
                    </span>
                  )}
                </div>
                {event.evidence_snippet && <p className="evidence-quote">{event.evidence_snippet}</p>}
                <button
                  className="link-button"
                  onClick={() => onOpenEvidence?.({ kind: "event", id: event.event_id })}
                  type="button"
                >
                  Open source page
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

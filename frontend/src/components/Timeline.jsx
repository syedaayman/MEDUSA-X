export default function Timeline({ events }) {
  return (
    <section className="card timeline-card">
      <div className="card-header">
        <div>
          <h2>Patient timeline</h2>
          <p>Illustrative sequence · not extracted from records</p>
        </div>
        <span className="demo-badge">Synthetic</span>
      </div>
      <div className="timeline-list">
        {events.map((event) => (
          <article className="timeline-item" key={event.id}>
            <time className="timeline-date" dateTime={event.date}>
              {event.displayDate}
            </time>
            <div className="timeline-content">
              <span className="timeline-marker" aria-hidden="true" />
              <strong>{event.title}</strong>
              <p>{event.description}</p>
              <span className="evidence-link">
                Example source: {event.source} · p. {event.page}
              </span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

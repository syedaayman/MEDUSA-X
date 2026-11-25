export default function ConflictPanel({ conflicts }) {
  return (
    <section className="card conflict-card">
      <div className="card-header">
        <div>
          <h2>Discrepancy review</h2>
          <p>Example only · requires clinician verification</p>
        </div>
        <span className="demo-badge">Mock</span>
      </div>
      {conflicts.map((conflict) => (
        <article className="conflict-item" key={conflict.id}>
          <div className="conflict-title">
            <span aria-hidden="true">!</span>
            {conflict.title}
          </div>
          <p>{conflict.description}</p>
          <p>
            Example sources: {conflict.sources.join(" · ")}. This synthetic discrepancy
            is not a real patient finding.
          </p>
        </article>
      ))}
    </section>
  );
}

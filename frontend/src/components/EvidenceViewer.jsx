export default function EvidenceViewer({ sources }) {
  return (
    <section className="card evidence-card">
      <div className="card-header">
        <div>
          <h2>Evidence viewer</h2>
          <p>Sample source links demonstrate planned provenance</p>
        </div>
        <span className="demo-badge">Mock excerpts</span>
      </div>
      {sources.map((source) => (
        <article className="evidence-row" key={source.id}>
          <div className="evidence-meta">
            <strong>{source.document}</strong>
            <span>Page {source.page}</span>
          </div>
          <p className="evidence-quote">“{source.excerpt}”</p>
        </article>
      ))}
    </section>
  );
}

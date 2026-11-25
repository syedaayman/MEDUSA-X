export default function SummaryPanel() {
  return (
    <section className="card summary-card">
      <div className="card-header">
        <div>
          <h2>Clinical summary</h2>
          <p>Illustrative layout · no findings generated</p>
        </div>
        <span className="demo-badge">Mock template</span>
      </div>
      <div className="summary-section">
        <h3>Reconciled history</h3>
        <p>
          No patient documents have been processed. A structured history will appear
          here only when supported by traceable evidence.
        </p>
      </div>
      <div className="summary-section">
        <h3>Uncertainty and open questions</h3>
        <p>
          Source coverage, conflicting statements, and missing dates will be identified
          explicitly in a future implementation.
        </p>
      </div>
      <div className="notice">
        This panel is a product mockup, not a medical assessment or treatment
        recommendation.
      </div>
    </section>
  );
}

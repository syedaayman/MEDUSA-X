import { Link } from "react-router-dom";

const features = [
  {
    icon: "↗",
    title: "Reconstruct a timeline",
    description:
      "Bring fragmented notes and reports into a chronological, source-linked view.",
  },
  {
    icon: "◇",
    title: "Surface discrepancies",
    description:
      "Make contradictory statements and medication differences easier to review.",
  },
  {
    icon: "◎",
    title: "Keep evidence in view",
    description:
      "Trace each future finding back to its originating document and page.",
  },
];

export default function Home() {
  return (
    <>
      <section className="hero-card">
        <div className="hero-content">
          <p className="eyebrow">Clinical record reconciliation</p>
          <h1>The clinical record that cannot be trusted.</h1>
          <p>
            MEDUSA-X is a decision-support prototype for organizing fragmented
            clinical documents, highlighting discrepancies, and keeping source
            evidence visible. It does not diagnose or prescribe.
          </p>
          <Link className="button" to="/dashboard">
            Explore the demo workspace
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
      <aside className="safety-banner">
        <span aria-hidden="true">ⓘ</span>
        <span>
          <strong>Prototype notice.</strong> The workspace currently displays synthetic
          examples only. Uploaded PDFs are read locally by the API and are not stored;
          OCR and clinical extraction are not implemented.
        </span>
      </aside>
    </>
  );
}

export default function PatientOverview({ patient }) {
  return (
    <section className="card patient-card">
      <div className="card-header">
        <div>
          <p className="eyebrow">Patient overview</p>
          <span className="patient-id">Synthetic demo record · {patient.id}</span>
        </div>
        <span className="demo-badge">Mock data</span>
      </div>
      <div className="patient-profile">
        <div className="avatar" aria-hidden="true">
          {patient.initials}
        </div>
        <div>
          <h2>{patient.name}</h2>
          <p>{patient.description}</p>
        </div>
      </div>
      <div className="patient-stats">
        <div>
          <span className="stat-label">Documents</span>
          <span className="stat-value">{patient.documentCount} mock</span>
        </div>
        <div>
          <span className="stat-label">Timeline entries</span>
          <span className="stat-value">{patient.timelineCount} mock</span>
        </div>
        <div>
          <span className="stat-label">Review status</span>
          <span className="stat-value">Demo only</span>
        </div>
      </div>
    </section>
  );
}

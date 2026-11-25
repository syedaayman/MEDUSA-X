import { useParams } from "react-router-dom";
import ConflictPanel from "../components/ConflictPanel.jsx";
import EvidenceViewer from "../components/EvidenceViewer.jsx";
import PatientOverview from "../components/PatientOverview.jsx";
import SummaryPanel from "../components/SummaryPanel.jsx";
import Timeline from "../components/Timeline.jsx";
import { demoPatient } from "../data/mockPatient.js";

export default function PatientDetails() {
  const { patientId } = useParams();
  const patient = {
    ...demoPatient.patient,
    id: patientId ?? demoPatient.patient.id,
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Patient record</p>
          <h1>Record details</h1>
          <p className="page-subtitle">
            This route uses a fixed synthetic example, not a backend patient record.
          </p>
        </div>
        <span className="demo-badge">Synthetic demo</span>
      </div>
      <div className="dashboard-grid">
        <div className="stack">
          <PatientOverview patient={patient} />
          <Timeline events={demoPatient.timeline} />
          <EvidenceViewer sources={demoPatient.sources} />
        </div>
        <div className="stack">
          <ConflictPanel conflicts={demoPatient.conflicts} />
          <SummaryPanel />
        </div>
      </div>
    </>
  );
}

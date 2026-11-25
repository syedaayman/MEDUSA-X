import ConflictPanel from "../components/ConflictPanel.jsx";
import EvidenceViewer from "../components/EvidenceViewer.jsx";
import FileUpload from "../components/FileUpload.jsx";
import PatientOverview from "../components/PatientOverview.jsx";
import SummaryPanel from "../components/SummaryPanel.jsx";
import Timeline from "../components/Timeline.jsx";
import { demoPatient } from "../data/mockPatient.js";

export default function Dashboard() {
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>Record overview</h1>
          <p className="page-subtitle">
            Review an illustrative record and test local PDF text extraction.
          </p>
        </div>
        <span className="demo-badge">All patient content is synthetic</span>
      </div>
      <div className="dashboard-grid">
        <div className="stack">
          <PatientOverview patient={demoPatient.patient} />
          <Timeline events={demoPatient.timeline} />
          <EvidenceViewer sources={demoPatient.sources} />
        </div>
        <div className="stack">
          <FileUpload />
          <ConflictPanel conflicts={demoPatient.conflicts} />
          <SummaryPanel />
        </div>
      </div>
    </>
  );
}

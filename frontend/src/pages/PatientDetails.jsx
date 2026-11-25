import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import AgentActivity from "../components/AgentActivity.jsx";
import ConflictPanel from "../components/ConflictPanel.jsx";
import EvidenceViewer from "../components/EvidenceViewer.jsx";
import PatientOverview from "../components/PatientOverview.jsx";
import SummaryPanel from "../components/SummaryPanel.jsx";
import Timeline from "../components/Timeline.jsx";
import {
  apiError,
  getAnalysis,
  getAnalysisActivity,
  getConflictEvidence,
  getConflicts,
  getEventEvidence,
  getPatient,
  getPatientAnalysis,
  getSummary,
  getTimeline,
  listDocuments,
  startAnalysis,
  updateReview,
} from "../services/api.js";
import { asList, fmtDate, fmtDateTime, statusTone } from "../lib/format.js";

const ACTIVE = new Set(["QUEUED", "RUNNING"]);

export default function PatientDetails() {
  const { patientId } = useParams();
  const [patient, setPatient] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [activity, setActivity] = useState([]);
  const [events, setEvents] = useState([]);
  const [conflicts, setConflicts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [patientError, setPatientError] = useState("");
  const [resultsError, setResultsError] = useState("");
  const [notice, setNotice] = useState("");
  const [reviewBusy, setReviewBusy] = useState("");
  const [evidence, setEvidence] = useState(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");
  const lastStatus = useRef(null);

  // Load timeline, conflicts, summary independently – failures do not crash the page.
  const loadResults = useCallback(async () => {
    setResultsError("");
    const [timelineResult, conflictResult, summaryResult] = await Promise.allSettled([
      getTimeline(patientId),
      getConflicts(patientId),
      getSummary(patientId),
    ]);
    if (timelineResult.status === "fulfilled") {
      setEvents(asList(timelineResult.value, "events"));
    } else {
      // Timeline error should not blank the page – leave existing state.
      console.warn("Timeline load failed:", timelineResult.reason);
    }
    if (conflictResult.status === "fulfilled") {
      setConflicts(asList(conflictResult.value, "conflicts"));
    } else {
      console.warn("Conflicts load failed:", conflictResult.reason);
    }
    if (summaryResult.status === "fulfilled") {
      setSummary(summaryResult.value ?? null);
    } else {
      console.warn("Summary load failed:", summaryResult.reason);
    }
    // Surface a non-fatal notice when any result endpoint returned an error.
    const failed = [timelineResult, conflictResult, summaryResult].filter(
      (r) => r.status === "rejected",
    );
    if (failed.length > 0) {
      setResultsError(
        `${failed.length} result panel(s) could not be loaded from the server. ` +
          "Documents and analysis status are still available.",
      );
    }
  }, [patientId]);

  // Load the most recent analysis run and its activity log.
  const loadAnalysis = useCallback(async () => {
    try {
      const runsData = await getPatientAnalysis(patientId);
      const runs = asList(runsData, "runs", "analysis");
      if (runs.length === 0) {
        setAnalysis(null);
        setActivity([]);
        return null;
      }
      const sorted = [...runs].sort((a, b) =>
        String(b.started_at ?? "").localeCompare(String(a.started_at ?? "")),
      );
      const latest = sorted[0];
      const runId = latest.analysis_run_id ?? latest.run_id ?? latest.id;
      const [detail, activityData] = await Promise.allSettled([
        getAnalysis(runId),
        getAnalysisActivity(runId),
      ]);
      const run = detail.status === "fulfilled" ? detail.value : latest;
      setAnalysis(run);
      setActivity(
        activityData.status === "fulfilled" ? asList(activityData.value, "activity", "events") : [],
      );
      return run;
    } catch (err) {
      console.warn("Analysis load failed:", err);
      return null;
    }
  }, [patientId]);

  // Initial full load: patient + documents (required), then analysis + results (optional).
  useEffect(() => {
    let cancelled = false;

    async function init() {
      setLoading(true);
      setPatientError("");
      setResultsError("");

      // Patient and documents are required; failure shows an error state.
      try {
        const [patientData, documentData] = await Promise.all([
          getPatient(patientId),
          listDocuments(patientId),
        ]);
        if (cancelled) return;
        setPatient(patientData);
        setDocuments(asList(documentData, "documents"));
      } catch (loadError) {
        if (!cancelled) setPatientError(apiError(loadError, "Could not load this patient."));
        setLoading(false);
        return;
      }

      setLoading(false);

      // Analysis and results are optional; failures surface as notices, not blank pages.
      if (cancelled) return;
      const run = await loadAnalysis();
      if (cancelled) return;

      // Always load results after page loads, regardless of run status.
      // If a run exists and is complete, results should already be persisted.
      await loadResults();
    }

    init();
    return () => {
      cancelled = true;
    };
  }, [patientId, loadAnalysis, loadResults]);

  // Polling loop while a run is active.
  const running = analysis ? ACTIVE.has(analysis.status) : false;

  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(async () => {
      try {
        const run = await loadAnalysis();
        if (run && !ACTIVE.has(run.status) && lastStatus.current !== run.status) {
          lastStatus.current = run.status;
          await loadResults();
          const patientData = await getPatient(patientId);
          setPatient(patientData);
        }
      } catch (pollError) {
        setNotice(apiError(pollError, "Lost contact with the analysis run."));
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [running, loadAnalysis, loadResults, patientId]);

  async function handleRun() {
    setNotice("");
    try {
      const run = await startAnalysis(patientId);
      lastStatus.current = run?.status ?? "QUEUED";
      setAnalysis(run ?? { status: "QUEUED" });
      await loadAnalysis();
    } catch (runError) {
      setNotice(apiError(runError, "Could not start the analysis run."));
    }
  }

  async function handleReview(conflictId, status, note) {
    setReviewBusy(conflictId);
    setNotice("");
    try {
      await updateReview(conflictId, status, note);
      const conflictData = await getConflicts(patientId);
      setConflicts(asList(conflictData, "conflicts"));
      setNotice(`Review status saved as ${status}.`);
    } catch (reviewError) {
      setNotice(apiError(reviewError, "Could not save the review decision."));
    } finally {
      setReviewBusy("");
    }
  }

  async function handleEvidence(target) {
    setEvidenceLoading(true);
    setEvidenceError("");
    setEvidence(null);
    try {
      const data =
        target.kind === "conflict"
          ? await getConflictEvidence(target.id)
          : await getEventEvidence(target.id);
      setEvidence(data);
    } catch (evidenceRequestError) {
      setEvidenceError(apiError(evidenceRequestError, "Could not load original evidence."));
    } finally {
      setEvidenceLoading(false);
    }
  }

  const counts = {
    documents: documents.length,
    entities: patient?.entity_count ?? 0,
    events: events.length,
    conflicts: conflicts.length,
    pending: conflicts.filter((conflict) => (conflict.review_status ?? "PENDING") === "PENDING")
      .length,
  };

  // Fatal state: patient could not be loaded at all.
  if (!loading && patientError && !patient) {
    return (
      <div className="page-heading">
        <div>
          <p className="eyebrow">Patient workspace</p>
          <h1>{patientId}</h1>
        </div>
        <p className="notice error">{patientError}</p>
        <button
          className="button"
          onClick={() => {
            setPatientError("");
            setLoading(true);
            // Trigger re-mount by using key – simpler: just reload
            window.location.reload();
          }}
          type="button"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Patient workspace</p>
          <h1>{patient?.display_name ?? patientId}</h1>
          <p className="page-subtitle">
            {patientId} · {documents.length} document(s) ·{" "}
            {analysis ? `last run ${analysis.status}` : "no analysis run yet"}
          </p>
        </div>
        <button className="button" disabled={running} onClick={handleRun} type="button">
          {running ? "Analysis running…" : "Run agent analysis"}
        </button>
      </div>

      {patientError && <p className="notice error">{patientError}</p>}
      {resultsError && <p className="notice warn">{resultsError}</p>}
      {notice && <p className="notice">{notice}</p>}
      {loading && <p className="empty-state">Loading patient workspace…</p>}

      <PatientOverview
        analysis={analysis}
        counts={counts}
        error={analysis?.error_message}
        isRunning={running}
        onRun={handleRun}
        patient={patient ?? { id: patientId }}
      />

      <div className="dashboard-grid top-gap">
        <div className="stack">
          <AgentActivity activity={activity} analysis={analysis} />

          <section className="card overview-card" aria-labelledby="documents-title">
            <div className="card-header">
              <div>
                <h2 id="documents-title">Source documents</h2>
                <p>Original uploads are never modified</p>
              </div>
              <span className="pill idle">{documents.length} file(s)</span>
            </div>
            {documents.length === 0 ? (
              <p className="empty-state">No documents attached to this patient yet.</p>
            ) : (
              documents.map((document) => (
                <div className="doc-row" key={document.id ?? document.document_id}>
                  <div>
                    <strong>{document.filename}</strong>
                    <p className="muted small">
                      {document.document_type ?? "UNCLASSIFIED"}
                      {document.document_date ? ` · ${fmtDate(document.document_date)}` : " · date unknown"}
                      {document.page_count ? ` · ${document.page_count} page(s)` : ""}
                      {document.uploaded_at ? ` · uploaded ${fmtDateTime(document.uploaded_at)}` : ""}
                    </p>
                  </div>
                  <span className={`pill ${statusTone(document.processing_status)}`}>
                    {document.processing_status ?? "UPLOADED"}
                  </span>
                </div>
              ))
            )}
          </section>

          <Timeline events={events} onOpenEvidence={handleEvidence} />
          <ConflictPanel
            busyId={reviewBusy}
            conflicts={conflicts}
            onOpenEvidence={handleEvidence}
            onReview={handleReview}
          />
        </div>

        <div className="stack">
          <SummaryPanel error={resultsError} loading={loading} summary={summary} />
          <EvidenceViewer
            error={evidenceError}
            evidence={evidence}
            loading={evidenceLoading}
            onClose={() => {
              setEvidence(null);
              setEvidenceError("");
            }}
          />
        </div>
      </div>
    </>
  );
}

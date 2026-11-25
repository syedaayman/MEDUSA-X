import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export const api = axios.create({ baseURL, timeout: 60_000 });

export function apiError(error, fallback = "Request failed") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg ?? String(item)).join("; ");
  if (detail && typeof detail === "object") {
    if (Array.isArray(detail.errors)) {
      return detail.errors.map((item) => `${item.filename}: ${item.error}`).join("; ");
    }
    return JSON.stringify(detail);
  }
  return error?.message ?? fallback;
}

export async function getHealth() {
  return (await api.get("/health")).data;
}

export async function uploadDocuments({ patientId, displayName, files, startAnalysis = true, reprocess = false }) {
  const form = new FormData();
  form.append("patient_id", patientId);
  if (displayName) form.append("display_name", displayName);
  form.append("start_analysis", String(startAnalysis));
  form.append("reprocess", String(reprocess));
  files.forEach((file) => form.append("files", file));
  return (await api.post("/api/upload", form)).data;
}

export async function startAnalysis(patientId) {
  return (await api.post(`/api/patient/${encodeURIComponent(patientId)}/process`)).data;
}

export async function getAnalysis(runId) {
  return (await api.get(`/api/analysis/${encodeURIComponent(runId)}`)).data;
}

export async function getAnalysisActivity(runId) {
  return (await api.get(`/api/analysis/${encodeURIComponent(runId)}/activity`)).data;
}

export async function getPatientAnalysis(patientId) {
  return (await api.get(`/api/patient/${encodeURIComponent(patientId)}/analysis`)).data;
}

export async function getPatient(patientId) {
  return (await api.get(`/api/patient/${encodeURIComponent(patientId)}`)).data;
}

export async function listDocuments(patientId) {
  return (await api.get(`/api/patient/${encodeURIComponent(patientId)}/documents`)).data;
}

export async function getDocumentPage(documentId, pageNumber) {
  return (await api.get(`/api/documents/${encodeURIComponent(documentId)}/pages/${pageNumber}`)).data;
}

export async function getTimeline(patientId) {
  return (await api.get(`/api/patient/${encodeURIComponent(patientId)}/timeline`)).data;
}

export async function getConflicts(patientId) {
  return (await api.get(`/api/patient/${encodeURIComponent(patientId)}/conflicts`)).data;
}

export async function getConflictEvidence(conflictId) {
  return (await api.get(`/api/conflicts/${encodeURIComponent(conflictId)}/evidence`)).data;
}

export async function updateReview(conflictId, reviewStatus, reviewerNote) {
  return (
    await api.patch(`/api/conflicts/${encodeURIComponent(conflictId)}/review`, {
      review_status: reviewStatus,
      reviewer_note: reviewerNote ?? null,
    })
  ).data;
}

export async function getSummary(patientId) {
  return (await api.get(`/api/patient/${encodeURIComponent(patientId)}/summary`)).data;
}

export async function listDatasets() {
  return (await api.get("/api/datasets")).data;
}

export async function getDatasetStatus(name) {
  return (await api.get(`/api/datasets/${encodeURIComponent(name)}/status`)).data;
}

export async function importDataset(name, limit = 25) {
  return (await api.post(`/api/datasets/${encodeURIComponent(name)}/import`, null, { params: { limit } })).data;
}

export async function evaluateDataset(name, evaluationType = "EXTRACTION", limit = 20) {
  return (
    await api.post(`/api/datasets/${encodeURIComponent(name)}/evaluate`, null, {
      params: { evaluation_type: evaluationType, limit },
    })
  ).data;
}

export async function getEvaluation(name) {
  return (await api.get(`/api/datasets/${encodeURIComponent(name)}/evaluation`)).data;
}

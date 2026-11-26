/** Small helpers shared by the MEDUSA-X UI. */

export function asList(data, ...keys) {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== "object") return [];
  for (const key of keys) {
    if (Array.isArray(data[key])) return data[key];
  }
  if (Array.isArray(data.items)) return data.items;
  if (Array.isArray(data.results)) return data.results;
  return [];
}

export function runIdOf(run) {
  return run?.run_id ?? run?.id ?? "";
}

export function fmtDate(value) {
  if (!value) return "Date unknown";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

export function fmtDateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function initials(name, fallback = "PX") {
  if (!name) return fallback;
  const parts = String(name).replace(/[^A-Za-z0-9 ]/g, " ").trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function statusTone(status) {
  const value = String(status ?? "").toUpperCase();
  if (["COMPLETED", "VERIFIED_POTENTIAL_CONFLICT", "REVIEWED", "OK", "IMPORTED"].includes(value)) return "ok";
  if (["RUNNING", "QUEUED", "PENDING", "PARTIAL", "NEEDS_HUMAN_REVIEW", "INSUFFICIENT_EVIDENCE"].includes(value)) return "warn";
  if (["FAILED", "ERROR", "UNRESOLVED", "NOT_IMPORTED"].includes(value)) return "bad";
  if (["SKIPPED", "NOT_A_CONFLICT", "DISMISSED"].includes(value)) return "idle";
  return "idle";
}

export function normaliseActivity(item) {
  return {
    id: item.id ?? `${item.agent_name ?? item.agent ?? "agent"}-${item.timestamp ?? item.created_at ?? Math.random()}`,
    agent: item.agent_name ?? item.agent ?? "AGENT",
    type: item.activity_type ?? "",
    message: item.activity_message ?? item.message ?? "",
    status: String(item.status ?? "RUNNING").toUpperCase(),
    timestamp: item.timestamp ?? item.created_at ?? null,
    detail: item.detail ?? null,
  };
}

export const AGENT_ORDER = [
  "ORCHESTRATOR",
  "DOCUMENT_INTELLIGENCE",
  "CLINICAL_STRUCTURING",
  "RECONCILIATION",
  "EVIDENCE_VERIFICATION",
  "TIMELINE_SUMMARY",
];

export const AGENT_LABELS = {
  ORCHESTRATOR: "Orchestrator",
  DOCUMENT_INTELLIGENCE: "Document Intelligence",
  CLINICAL_STRUCTURING: "Clinical Structuring",
  RECONCILIATION: "Reconciliation",
  EVIDENCE_VERIFICATION: "Evidence Verification",
  TIMELINE_SUMMARY: "Timeline & Summary",
};

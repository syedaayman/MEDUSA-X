# MEDUSA-X architecture

MEDUSA-X is a local-first clinical record reconciliation prototype. Its intended
backend path is document ingestion → text extraction/OCR → clinical fact extraction →
timeline and discrepancy analysis → evidence validation → clinician-reviewed
summary. Every future finding must retain document and page provenance and express
uncertainty.

## Current foundation

- `frontend/`: Vite, React Router, Axios, and Tailwind CSS; the dashboard reads from the
  live API rather than synthetic mock data.
- `backend/`: FastAPI application with typed response models, local PDF text extraction
  using PyMuPDF (with a stdlib fallback), SQLite persistence, and the deterministic
  ingestion → extraction → classification → entity extraction → reconciliation →
  verification → timeline/summary pipeline.
- `backend/services/`: an explicitly invoked, environment-configured OpenAI SDK
  interface (`generate_text`); when `OPENAI_API_KEY` is set, the Agents-SDK coordinator
  layer additionally drives the orchestrator team. Credentials are not needed to start
  the API, and the health endpoint reports whether the model layer is enabled.
- `sample_data/`: instructions only; datasets and patient documents are not checked in.

The upload endpoint persists the PDF bytes and its page-level text in SQLite, returns
page text per page, and flags scanned pages that need OCR. `/api/patients`,
`/api/patient/{id}/entities`, `/api/patient/{id}/timeline`,
`/api/patient/{id}/conflicts`, `/api/patient/{id}/summary` and
`/api/patient/{id}/analysis` serve the real stored data; dataset patients use the
`synthea:` namespace and never appear as uploaded patients.

## Planned boundaries

SQLite is the only datastore: patient records, documents, extracted clinical entities,
timeline events, conflicts, review decisions, analysis runs, agent activity, summaries,
dataset imports and evaluations all persist in one local file, with no external
database service or credentials. Access control, retention and audit policies must be
designed before handling real records. All LLM access belongs on the backend. The
frontend must never receive model credentials.

## Safety boundary

This is decision support, not an autonomous diagnosis, prescribing, or clinical
workflow system. A qualified clinician must verify source documents, extracted facts,
conflicts, and any generated summary. The current mock content is not a medical
finding.

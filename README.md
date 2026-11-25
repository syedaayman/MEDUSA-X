# MEDUSA-X

**AI-powered medical record intelligence, reconciliation and clinical timeline platform.**

MEDUSA-X ingests a patient's fragmented medical documents, extracts structured clinical facts with
page-level provenance, reconstructs a chronological history, and then runs a coordinated team of
agents that compare records, propose discrepancies, and independently re-verify each proposal
against the original page text before anything is shown.

> **Prototype notice.** MEDUSA-X is a research/hackathon prototype. It is **not** a medical device,
> it is not production-ready, and it is not compliant with healthcare regulation. It never decides
> which clinical record is correct, never prescribes or advises treatment, and never replaces
> clinician judgement. Every finding is a *potential* discrepancy for human review.

---

## 1. What it does

1. Upload one or more medical PDFs for a patient.
2. PyMuPDF extracts page-level text; scanned pages are marked `OCR_REQUIRED` instead of pretending
   content was read.
3. Documents are classified (type + clinical date, never the upload date) and clinical entities are
   extracted with document, page, snippet, confidence and date precision.
4. The orchestrator retrieves patient context and decides which specialists must run.
5. Comparable medications, diagnoses, allergies and laboratory results are compared — like with
   like, respecting clinical dates and status.
6. Every proposed discrepancy is re-verified against the stored page text; unsupported findings are
   rejected and ambiguous ones escalate to human review.
7. A chronological timeline and an evidence-backed summary are generated and stored.
8. The React dashboard shows real agent activity, findings, evidence and review decisions.

## 2. Architecture

```
React + Vite dashboard
        │  Axios (VITE_API_BASE_URL)
        ▼
FastAPI backend  ── SQLite (patients, documents, pages, entities, conflicts, runs, activity, audit)
        │
        ├── ingestion/        PDF validation, page extraction, classification, quality
        ├── clinical/         deterministic extraction, reconcilers, verifier, timeline, summary
        ├── agents/           orchestrator + 5 specialists, real tools, OpenAI Agents SDK runtime
        ├── datasets/         Synthea + EkaCare adapters, import runs, isolation, evaluation
        └── api/              upload, patient, report, dataset routes
```

### The agent team

| Agent | Responsibility | Real tools it uses |
|---|---|---|
| **MEDUSA-X Orchestrator** | Retrieves patient context, decides which specialists run, passes structured results, requests re-extraction, final quality check | `get_patient_context`, `read_document`, `save_clinical_entities`, `save_conflict`, `request_human_review` |
| **Document Intelligence** | Classifies documents, finds sections/pages, reports extraction quality and missing content | `read_document`, `get_document_page`, `classify_document` |
| **Clinical Structuring** | Extracts diagnoses, medications (dose/frequency/route/duration/status), allergies, procedures, labs, vitals, plan | `extract_clinical_entities`, `save_clinical_entities` |
| **Medical Record Reconciliation** | Compares comparable entities across documents, proposes discrepancies with reason and priority | `get_clinical_entities`, `compare_medications`, `compare_diagnoses`, `compare_allergies`, `compare_laboratory_results` |
| **Evidence Verification** | Re-reads original pages, confirms values/pages/patient identity, decides `VERIFIED_POTENTIAL_CONFLICT` / `NOT_A_CONFLICT` / `INSUFFICIENT_EVIDENCE` / `NEEDS_HUMAN_REVIEW` | `get_event_evidence`, `verify_evidence`, `request_human_review` |
| **Timeline & Summary** | Builds the chronological record and the evidence-backed summary | `build_patient_timeline`, `generate_patient_summary` |

### Deterministic core, model layer on top

This is deliberate and important:

* The **deterministic pipeline is always the source of truth** for stored clinical facts. It needs no
  API key, is reproducible, and is what the tests exercise.
* When `OPENAI_API_KEY` is set, the **OpenAI Agents SDK** runtime additionally drives the specialist
  agents: they choose tools, read original pages and can escalate findings. Model output is never
  written over stored evidence without passing the same verification checks.
* With no key, `/health` reports the model layer as disabled and the workflow still completes
  end-to-end. Nothing is faked: the UI shows which layer produced each result.

## 3. Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite, React Router, Tailwind CSS, Axios |
| Backend | Python 3, FastAPI, Uvicorn |
| Agents | OpenAI Agents SDK (`openai-agents`), optional model layer |
| Extraction | PyMuPDF |
| Validation | Pydantic v2, pydantic-settings |
| Storage | SQLite (default). Supabase credentials are optional and unused by default |
| Datasets | Python adapters for FHIR JSON, Synthea CSV, image/text/JSON evaluation data |

## 4. Quick start

Backend (from the repository root):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env      # optional: add OPENAI_API_KEY
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Swagger: <http://127.0.0.1:8000/docs> · Health: <http://127.0.0.1:8000/health>

Frontend (second terminal):

```bash
cd frontend
npm install
cp .env.example .env                      # VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

Open <http://127.0.0.1:5173>. The dashboard works with the backend down: it shows an explicit
"API disconnected" state instead of fake data.

## 5. Environment variables

See `backend/.env.example` and `frontend/.env.example`. Only `VITE_API_BASE_URL` is exposed to the
browser — **never** put a model or Supabase secret in a `VITE_` variable. OpenAI and Supabase
credentials stay in the backend process.

## 6. API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Status, storage mode, whether the model layer is configured |
| POST | `/api/upload` | Multipart PDF upload (`patient_id`, `display_name`, `start_analysis`, `reprocess`, `files`) |
| GET | `/api/patients` | Uploaded patients with live counts |
| GET | `/api/patient/{patient_id}` | Patient record |
| GET | `/api/patient/{patient_id}/documents` | Documents with extraction status |
| GET | `/api/documents/{document_id}` | Single document |
| GET | `/api/documents/{document_id}/pages/{page}` | Original page text |
| GET | `/api/patient/{patient_id}/entities` | Structured clinical entities |
| POST | `/api/patient/{patient_id}/process` | Start an analysis run |
| GET | `/api/analysis/{run_id}` | Run status, metrics, quality checks |
| GET | `/api/analysis/{run_id}/activity` | Real agent activity events |
| GET | `/api/patient/{patient_id}/analysis` | Run history |
| GET | `/api/patient/{patient_id}/timeline` | Chronological events |
| GET | `/api/patient/{patient_id}/conflicts` | Discrepancies with verification status |
| GET | `/api/conflicts/{conflict_id}` | Single discrepancy |
| PATCH | `/api/conflicts/{conflict_id}/review` | Record a human review decision (audited) |
| GET | `/api/conflicts/{conflict_id}/evidence` | Original page text for both sides |
| GET | `/api/events/{event_id}/evidence` | Original page text for a timeline event |
| GET | `/api/patient/{patient_id}/summary` | Evidence-backed summary |
| GET | `/api/patient/{patient_id}/audit` | Audit trail |
| GET | `/api/datasets` | Registered datasets, availability, origin labels |
| GET | `/api/datasets/{name}/status` | Import status and last run |
| POST | `/api/datasets/{name}/import` | Import local dataset files |
| POST | `/api/datasets/{name}/evaluate` | Run an evaluation (`evaluation_type`, `limit`) |
| GET | `/api/datasets/{name}/evaluation` | Stored evaluation results |

Long-running work happens in a background run: upload returns an `analysis_run_id` immediately and
the UI polls `/api/analysis/{run_id}` plus `/activity`.

## 7. Datasets

Dataset files are **not** committed. Download them yourself (respecting each licence) and place them
here:

```
sample_data/datasets/
├── synthea/                                  # FHIR R4 Bundle JSON and/or Synthea CSV export
├── ekacare_medical_records_parsing/          # document images + annotations
├── ekacare_clinical_note_generation/         # narratives + structured JSON
└── ekacare_medical_history_summarisation/    # histories + reference summaries
```

Sources: [Synthea](https://github.com/synthetichealth/synthea) ·
[EkaCare datasets](https://huggingface.co/ekacare/datasets) ·
[EkaCare announcement](https://www.eka.care/services/advancing-healthcare-ai-evaluation-in-india-ekacare-releases-four-evaluation-datasets)

Behaviour you can rely on:

* `GET /api/datasets` reports per-dataset availability, file counts and formats **without** importing
  anything at startup.
* If files are missing, `POST /api/datasets/{name}/import` records an honest failed import run with
  error details instead of inventing records.
* Synthea records never pass through the PDF pipeline and never appear as uploaded patients: they use
  the `synthea:<source-id>` namespace and `data_origin = SYNTHETIC_DATASET`. EkaCare evaluation data is
  labelled `EKACARE_EVALUATION`.
* Evaluation compares generated output against ground truth that actually exists in the files and
  reports real sample counts; unavailable ground truth is reported as unavailable, not as a score.

## 8. Tests

```bash
pytest backend/tests -q
```

Coverage highlights (`backend/tests/`):

* single-document extraction and timeline, and no invented cross-document conflicts;
* multi-document shared context, source references and chronological ordering;
* medication discrepancy proposed **and** verified against both source pages;
* a legitimate dose change over time not reported as a high-severity conflict;
* fabricated finding rejected as insufficient evidence;
* duplicate upload detection, invalid PDF handling, missing-API-key behaviour;
* simulated specialist failure recorded while the run still terminates;
* human review decision persisted and audited;
* Synthea FHIR normalisation with synthetic origin labels, missing-dataset honesty, dataset isolation.

Tests run against a temporary SQLite database and document store with no OpenAI key, so they are
deterministic and require no credentials.

## 9. Demo walkthrough

1. `uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload`, then `npm run dev` in `frontend`.
2. Open the dashboard; confirm the health badge shows the API connected.
3. Upload a discharge summary and a prescription for the same patient (two PDFs, one form).
4. Watch the processing centre: orchestrator, document intelligence, structuring, reconciliation,
   evidence verification, timeline & summary.
5. Open the discrepancy: both values, both documents, both pages, the verification decision.
6. Click through to the evidence viewer and read the original page text.
7. Record a review decision; refresh the page — the decision is still there.
8. Open the timeline, filter by category, and open any event's evidence.
9. Read the summary, then the dataset panel for import/evaluation status.

## 10. Known limitations

* OCR is not bundled: scanned PDFs are flagged `OCR_REQUIRED` rather than silently empty.
* The model layer is optional; without a key the agents run the deterministic tool chain only.
* Dataset adapters depend on the exact files you place locally; unverified layouts fail loudly.
* SQLite is single-node; no multi-user authentication or tenant isolation beyond patient scoping.
* Not for clinical use, and not a substitute for medical record review.

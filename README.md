# MEDUSA-X

**The Clinical Record That Cannot Be Trusted**

MEDUSA-X is a clinical record reconciliation prototype that aims to organize
fragmented medical documents into a chronological, evidence-linked view. It is
designed to help people review inconsistent records—not to make autonomous clinical
decisions.

> **Prototype and safety notice:** This project is not a medical device or clinical
> service. It does not diagnose, prescribe, or replace a qualified healthcare
> professional. The dashboard's example patient, timeline, conflicts, and excerpts
> are synthetic mock data. Do not upload real patient records to this prototype.

## Problem statement

Patient histories can be distributed across prescriptions, laboratory reports,
admission notes, and discharge summaries. Important dates and instructions may be
difficult to reconcile, and a summary can be misleading if its source cannot be
checked. MEDUSA-X explores a traceable workflow that keeps source evidence and
uncertainty visible while organizing those records for human review.

## Project objectives

- Accept fragmented clinical documents and extract their content.
- Reconstruct a chronological patient history.
- Surface contradictory diagnoses and medication discrepancies.
- Identify missing information without silently filling gaps.
- Link every future extracted fact to its source document and page.
- Present a structured summary with uncertainty clearly indicated.
- Keep clinical review with a qualified human; never autonomously diagnose or
  prescribe.

## Core features and current boundary

- **Local PDF text extraction:** the starter API reads selectable PDF text page by
  page using PyMuPDF. Uploads are processed in memory, limited to 20 MB, and not
  persisted.
- **Dashboard prototype:** responsive React pages preview an overview, document
  upload, timeline, discrepancies, evidence, and summary.
- **Synthetic examples:** all visible patient content in the dashboard is mock data
  and labeled as such. It is not created by the backend extractor.
- **Explicit placeholders:** OCR, document classification, clinical entity
  extraction, reconciliation, and evidence validation are not implemented. Empty
  patient API responses are intentional; the backend does not invent findings.
- **Integrations not active by default:** Supabase and the configurable LLM service
  require credentials and are not called during startup or upload.

## Technology stack

| Area | Technologies |
| --- | --- |
| Frontend | React, Vite, JavaScript, Tailwind CSS, React Router, Axios |
| Backend | Python, FastAPI, Pydantic, Uvicorn, PyMuPDF |
| OCR (planned) | Tesseract integration placeholder |
| Database and storage (planned) | Supabase PostgreSQL and Supabase Storage |
| LLM (planned) | Backend-only configurable provider; OpenAI interface configured by environment |

No model is trained. No data or credentials are downloaded or included automatically.

## Architecture overview

```text
React dashboard ── Axios ── FastAPI
                                ├── PDF text extraction (PyMuPDF; in memory)
                                ├── OCR / clinical processing (placeholders)
                                ├── Supabase service (lazy; credentials required)
                                └── LLM service (explicit call; backend credentials required)
```

See [docs/architecture.md](docs/architecture.md) for boundaries and the planned data
flow, and [docs/api_contract.md](docs/api_contract.md) for the starter API responses.

## Folder structure

```text
MEDUSA-X/
├── backend/
│   ├── main.py, config.py, requirements.txt, .env.example
│   ├── api/                 # Upload, patient, report routes
│   ├── ingestion/           # PDF extraction and OCR/classifier placeholders
│   ├── clinical/            # Entity, timeline, and reconciliation placeholders
│   ├── agents/              # Future workflow placeholders
│   ├── validation/          # Conflict, missing-data, evidence placeholders
│   ├── models/              # Pydantic request/response and domain schemas
│   ├── services/            # Lazy Supabase and configurable LLM services
│   └── utils/
├── frontend/
│   ├── index.html, package.json, vite.config.js
│   └── src/
│       ├── components/      # Navigation, upload, timeline, evidence, summary
│       ├── pages/           # Home, dashboard, patient details
│       ├── services/        # Backend API client
│       └── data/            # Synthetic display data only
├── sample_data/             # Safe sample-data instructions
├── docs/                    # Architecture and API contract
├── tests/                   # Test-data guidance and smoke checks
└── README.md
```

## Team responsibilities

| Team member | Responsibilities |
| --- | --- |
| Ayman | Backend architecture, orchestration, API integration, and Supabase |
| Misba | Document ingestion, clinical entity extraction, and timeline reconstruction |
| Suha | React frontend, dashboard, and visualization |
| Ayesha | Contradiction detection, missing-data detection, evidence validation, and testing |

## Local installation

Requirements: Python 3.10 or later, Node.js/npm, and a terminal. No database or API
credentials are required for the initial local demo.

### 1. Start the FastAPI backend

In PowerShell, from the repository root:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

The API listens at `http://127.0.0.1:8000`. Check `http://127.0.0.1:8000/health` or
open the interactive API documentation at `http://127.0.0.1:8000/docs`.

### 2. Start the React frontend

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`). The
dashboard uses synthetic mock content. Its PDF upload sends a file to the local API
for selectable-text extraction; scanned pages are reported as needing OCR, and no
clinical interpretation is produced.

### Environment variables

Backend settings are documented in [backend/.env.example](backend/.env.example). Copy
it to `backend/.env` and configure only when needed:

| Variable | Use |
| --- | --- |
| `CORS_ORIGINS` | Comma-separated local frontend origins; defaults to `http://localhost:5173,http://127.0.0.1:5173`. |
| `SUPABASE_URL` | Supabase project URL; leave empty until configured. |
| `SUPABASE_SECRET_KEY` | Backend-only Supabase secret; never expose in frontend code. |
| `LLM_PROVIDER` | Provider selector; currently the implemented option is `openai`. |
| `OPENAI_API_KEY` | Backend-only key; no LLM call happens unless a service call is explicitly made. |
| `OPENAI_MODEL` | OpenAI model name; defaults to `gpt-4o-mini`. |

Never commit `.env` files, keys, or patient documents. Frontend configuration must
never contain Supabase secret keys or LLM API keys. An optional
`VITE_API_BASE_URL` can override the local API URL; it is not for secrets.

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | API process health |
| `POST` | `/api/upload` | In-memory PDF selectable-text extraction (multipart field `file`) |
| `GET` | `/api/patient/{patient_id}` | Patient record availability; currently empty |
| `GET` | `/api/patient/{patient_id}/timeline` | Timeline; currently empty |
| `GET` | `/api/patient/{patient_id}/conflicts` | Conflict list; currently empty |
| `GET` | `/api/patient/{patient_id}/summary` | Summary; currently unavailable |

The upload endpoint accepts PDFs up to 20 MB and responds with page text and a list
of pages without selectable text. It rejects non-PDF and unreadable files. Uploads
are not stored. Patient endpoints return no clinical data until real integrations
and evidence-backed processing are implemented.

## Dataset usage plan

Datasets will not be automatically downloaded or committed.

1. [EkaCare Medical Records Parsing Validation Set](https://huggingface.co/collections/ekacare/ekacare-medical-public-datasets):
   evaluate extraction on Indian prescriptions and laboratory reports, subject to
   dataset access and license terms.
2. [Synthea](https://synthetichealth.github.io/synthea/): generate synthetic
   longitudinal patient histories to test timeline reconstruction and reconciliation.

See [sample_data/README.md](sample_data/README.md) for safe sample handling. Use only
synthetic, de-identified, or explicitly authorized data; do not commit patient
documents or dataset dumps.

## Implementation status

- [x] Initial backend and frontend project structure.
- [x] Health endpoint and empty typed patient/timeline/conflict/summary responses.
- [x] In-memory PDF text extraction with page references and clear OCR status.
- [x] Synthetic, labeled dashboard and working local PDF upload flow.
- [x] Environment examples and lazy integration service modules.
- [ ] Tesseract OCR and document classification.
- [ ] Clinical extraction, timeline reconstruction, reconciliation, and evidence validation.
- [ ] Supabase persistence, storage, access control, and audit design.
- [ ] Automated unit/integration tests and production safety review.

## Future improvements

- Implement OCR with explicit quality and review states.
- Define provenance-preserving clinical schemas and extraction evaluation.
- Add robust date normalization, chronology handling, and conflict adjudication.
- Integrate Supabase only after access control, encryption, retention, and audit
  requirements are agreed.
- Add clinician review workflows, uncertainty display, and usability evaluation.
- Build synthetic-data tests and validate against approved, licensed datasets.

## Privacy and clinical safety

This foundation is for local development and synthetic demonstrations, not
production or clinical use. Do not enter real personal health information or upload
real patient records. The API currently reads PDFs in memory, but this is not a
substitute for a privacy/security assessment. Before any authorized clinical data is
handled, the team must implement and review authentication, authorization,
encryption, secure document storage, retention/deletion, audit logging, threat
controls, regulatory obligations, and incident response.

Any future extracted fact, discrepancy, or summary must be traceable to the original
source and page, disclose uncertainty and missing data, and be reviewed by a
qualified clinician. MEDUSA-X is clinical decision support—not an autonomous
diagnosis or prescribing system.

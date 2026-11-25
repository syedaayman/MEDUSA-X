# MEDUSA-X architecture

MEDUSA-X is a local-first clinical record reconciliation prototype. Its intended
backend path is document ingestion → text extraction/OCR → clinical fact extraction →
timeline and discrepancy analysis → evidence validation → clinician-reviewed
summary. Every future finding must retain document and page provenance and express
uncertainty.

## Current foundation

- `frontend/`: Vite, React Router, Axios, and Tailwind CSS. Its dashboard is explicitly
  populated with synthetic mock data.
- `backend/`: FastAPI application with typed response models and local PDF text
  extraction using PyMuPDF.
- `backend/services/`: lazy Supabase configuration and an explicitly invoked,
  environment-configured LLM interface. Credentials are not needed to start the API.
- `sample_data/`: instructions only; datasets and patient documents are not checked in.

The upload endpoint reads a PDF in memory and returns page text; it does not persist
uploads or infer clinical facts. Empty patient API responses are intentional until a
trusted data source is connected. OCR and clinical processing modules are explicit
placeholders.

## Planned boundaries

Supabase PostgreSQL is the intended structured store and Supabase Storage the intended
document store. Service integration, access control, retention, and audit policies
must be designed before handling real records. All LLM access belongs on the backend.
The frontend must never receive Supabase secret keys or LLM credentials.

## Safety boundary

This is decision support, not an autonomous diagnosis, prescribing, or clinical
workflow system. A qualified clinician must verify source documents, extracted facts,
conflicts, and any generated summary. The current mock content is not a medical
finding.

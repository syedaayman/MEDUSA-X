# API contract (starter)

Run the API from `backend/` at `http://127.0.0.1:8000`. Interactive OpenAPI docs are
available at `/docs`.

| Method | Path | Starter behavior |
| --- | --- | --- |
| `GET` | `/health` | Returns `{"status":"ok"}`. |
| `POST` | `/api/upload` | Accepts multipart field `file` containing a PDF; returns selectable text per page and pages requiring OCR. Uploads are processed in memory, not persisted. |
| `GET` | `/api/patient/{patient_id}` | Returns the requested identifier with `data_status: "no_records"` and no clinical data. |
| `GET` | `/api/patient/{patient_id}/timeline` | Returns an empty timeline with `data_status: "no_records"`. |
| `GET` | `/api/patient/{patient_id}/conflicts` | Returns an empty conflict list with `data_status: "no_records"`. |
| `GET` | `/api/patient/{patient_id}/summary` | Returns a null summary with `data_status: "no_records"`. |

Non-PDF uploads receive `415`; empty or unreadable PDFs receive `400`. OCR,
classification, clinical extraction, reconciliation, and summary generation are not
implemented. No patient findings are fabricated by these endpoints.

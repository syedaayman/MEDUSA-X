"""Data access layer. Every agent tool and API route reads/writes through here."""

from __future__ import annotations

import json
from typing import Any, Iterable

from backend.db import db, new_id, utc_now

JSON_FIELDS = {
    "ocr_required_pages",
    "attributes",
    "related_entity_ids",
    "compared_entity_ids",
    "compared_values",
    "source_references",
    "sections",
    "uncertainty_notes",
    "document_ids",
    "warnings",
    "metrics",
    "detail",
    "metadata",
    "payload",
    "generated_output",
    "reference_output",
    "evaluation_details",
    "error_details",
}


def _load(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _dump(value: Any) -> str:
    return json.dumps(value if value is not None else {})


def row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict with JSON fields decoded."""
    if row is None:
        return {}
    data = dict(row)
    for field in JSON_FIELDS & data.keys():
        default = [] if field.endswith(("s", "s")) else {}
        data[field] = _load(data[field], default)
    # Name unifier: stored rows use the DB column name (clinical_entities and
    # timeline_events use document_id; timeline rows were stored with
    # source_document_id). Producers and consumers use both spellings
    # (source_document_id in reconcilers/verifier, document_id in
    # report_routes/tools), so expose each alias when the other is missing.
    if data.get("document_id") is not None and "source_document_id" not in data:
        data["source_document_id"] = data["document_id"]
    elif data.get("source_document_id") is not None and "document_id" not in data:
        data["document_id"] = data["source_document_id"]
    return data


# --------------------------------------------------------------- patients

def ensure_patient(patient_id: str, display_name: str | None = None, data_origin: str = "USER_UPLOAD") -> dict:
    """Create the patient when missing; never overwrite existing values."""
    with db() as conn:
        existing = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        if existing:
            return row_to_dict(existing)
        now = utc_now()
        conn.execute(
            "INSERT INTO patients (id, display_name, data_origin, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (patient_id, display_name or patient_id, data_origin, now, now),
        )
        return {"id": patient_id, "display_name": display_name or patient_id, "data_origin": data_origin}


def get_patient(patient_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_patients(data_origin: str | None = None) -> list[dict]:
    query = "SELECT * FROM patients"
    params: tuple = ()
    if data_origin:
        query += " WHERE data_origin = ?"
        params = (data_origin,)
    query += " ORDER BY created_at DESC"
    with db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(row) for row in rows]


def touch_patient(patient_id: str) -> None:
    with db() as conn:
        conn.execute("UPDATE patients SET updated_at = ? WHERE id = ?", (utc_now(), patient_id))


# -------------------------------------------------------------- documents

def create_document(
    patient_id: str,
    filename: str,
    content_hash: str,
    storage_path: str | None,
    data_origin: str = "USER_UPLOAD",
) -> tuple[dict, bool]:
    """Insert a document. Returns (document, created) — duplicates reuse the row."""
    with db() as conn:
        existing = conn.execute(
            "SELECT * FROM documents WHERE patient_id = ? AND content_hash = ?",
            (patient_id, content_hash),
        ).fetchone()
        if existing:
            return row_to_dict(existing), False
        doc_id = new_id("doc")
        conn.execute(
            """INSERT INTO documents
               (id, patient_id, filename, content_hash, storage_path, data_origin, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, patient_id, filename, content_hash, storage_path, data_origin, utc_now()),
        )
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return row_to_dict(row), True


def get_document(document_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_documents(patient_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE patient_id = ? ORDER BY created_at", (patient_id,)
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def save_pages(document_id: str, pages: Iterable[dict]) -> None:
    with db() as conn:
        conn.execute("DELETE FROM document_pages WHERE document_id = ?", (document_id,))
        conn.executemany(
            """INSERT INTO document_pages (document_id, page_number, text, char_count, ocr_required)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (
                    document_id,
                    int(page["page_number"]),
                    page.get("text") or "",
                    len(page.get("text") or ""),
                    1 if page.get("ocr_required") else 0,
                )
                for page in pages
            ],
        )


def get_page(document_id: str, page_number: int) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM document_pages WHERE document_id = ? AND page_number = ?",
            (document_id, int(page_number)),
        ).fetchone()
    return dict(row) if row else None


def list_pages(document_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM document_pages WHERE document_id = ? ORDER BY page_number", (document_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def update_document(document_id: str, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = [value for value in fields.values()]
    values.append(document_id)
    with db() as conn:
        conn.execute(f"UPDATE documents SET {assignments} WHERE id = ?", values)


def document_text(document_id: str, max_chars: int | None = None) -> str:
    """Return page-marked text for a document, optionally bounded."""
    chunks: list[str] = []
    for page in list_pages(document_id):
        chunks.append(f"[page {page['page_number']}]\n{page['text']}")
    text = "\n\n".join(chunks)
    return text[:max_chars] if max_chars else text


# --------------------------------------------------------------- entities

def save_entities(patient_id: str, entities: Iterable[dict]) -> int:
    """Replace entities for the documents present in this batch."""
    entities = list(entities)
    document_ids = {e.get("source_document_id") for e in entities if e.get("source_document_id")}
    with db() as conn:
        for doc_id in document_ids:
            conn.execute("DELETE FROM clinical_entities WHERE document_id = ?", (doc_id,))
        conn.executemany(
            """INSERT INTO clinical_entities
               (id, patient_id, document_id, category, original_value, normalized_value,
                clinical_date, date_precision, source_type, source_record_id, source_page,
                evidence_snippet, confidence, verification_status, data_origin, attributes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    entity.get("id") or new_id("ent"),
                    patient_id,
                    entity.get("source_document_id"),
                    entity["category"],
                    entity.get("original_value"),
                    entity.get("normalized_value"),
                    entity.get("clinical_date"),
                    entity.get("date_precision") or "UNKNOWN",
                    entity.get("source_type") or "DOCUMENT",
                    entity.get("source_record_id"),
                    entity.get("source_page"),
                    entity.get("evidence_snippet"),
                    entity.get("confidence"),
                    entity.get("verification_status") or "UNVERIFIED",
                    entity.get("data_origin") or "USER_UPLOAD",
                    _dump(entity.get("attributes") or {}),
                    utc_now(),
                )
                for entity in entities
            ],
        )
    return len(entities)


def list_entities(
    patient_id: str,
    categories: list[str] | None = None,
    document_id: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM clinical_entities WHERE patient_id = ?"
    params: list[Any] = [patient_id]
    if categories:
        placeholders = ", ".join("?" for _ in categories)
        query += f" AND category IN ({placeholders})"
        params.extend(categories)
    if document_id:
        query += " AND document_id = ?"
        params.append(document_id)
    query += " ORDER BY clinical_date, created_at"
    with db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(row) for row in rows]


def get_entity(entity_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM clinical_entities WHERE id = ?", (entity_id,)).fetchone()
    return row_to_dict(row) if row else None


def count_entities(patient_id: str) -> int:
    with db() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS total FROM clinical_entities WHERE patient_id = ?", (patient_id,)
        ).fetchone()["total"]


# ---------------------------------------------------------------- timeline

def save_timeline(patient_id: str, events: Iterable[dict]) -> int:
    events = list(events)
    with db() as conn:
        conn.execute("DELETE FROM timeline_events WHERE patient_id = ?", (patient_id,))
        conn.executemany(
            """INSERT INTO timeline_events
               (id, patient_id, event_date, date_precision, category, description,
                related_entity_ids, source_document_id, source_document_name, source_page,
                evidence_snippet, verification_status, data_origin, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    event.get("event_id") or new_id("evt"),
                    patient_id,
                    event.get("event_date"),
                    event.get("date_precision") or "UNKNOWN",
                    event["category"],
                    event["description"],
                    _dump(event.get("related_entity_ids") or []),
                    event.get("source_document_id"),
                    event.get("source_document_name"),
                    event.get("source_page"),
                    event.get("evidence_snippet"),
                    event.get("verification_status") or "UNVERIFIED",
                    event.get("data_origin") or "USER_UPLOAD",
                    utc_now(),
                )
                for event in events
            ],
        )
    return len(events)


def list_timeline(patient_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM timeline_events WHERE patient_id = ?
               ORDER BY COALESCE(event_date, '9999-99-99'), created_at""",
            (patient_id,),
        ).fetchall()
    result = [row_to_dict(row) for row in rows]
    # Inject event_id alias: DB column is "id" but Pydantic schema requires "event_id".
    for item in result:
        item.setdefault("event_id", item["id"])
    return result


def get_event(event_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM timeline_events WHERE id = ?", (event_id,)).fetchone()
    return row_to_dict(row) if row else None


# --------------------------------------------------------------- conflicts

def save_conflict(patient_id: str, conflict: dict, analysis_run_id: str | None = None) -> dict:
    conflict_id = conflict.get("conflict_id") or conflict.get("id") or new_id("cnf")
    now = utc_now()
    with db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO conflicts
               (id, patient_id, analysis_run_id, category, description, compared_entity_ids,
                compared_values, source_references, reason, possible_explanation, severity,
                confidence, verification_status, verification_reason, review_status,
                requires_human_review, data_origin, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                conflict_id,
                patient_id,
                analysis_run_id,
                conflict["category"],
                conflict["description"],
                _dump(conflict.get("compared_entity_ids") or []),
                _dump(conflict.get("compared_values") or []),
                _dump(conflict.get("source_references") or []),
                conflict.get("reason"),
                conflict.get("possible_explanation"),
                conflict.get("severity") or "MEDIUM",
                conflict.get("confidence"),
                conflict.get("verification_status") or "UNVERIFIED",
                conflict.get("verification_reason"),
                conflict.get("review_status") or "PENDING",
                1 if conflict.get("requires_human_review", True) else 0,
                conflict.get("data_origin") or "USER_UPLOAD",
                now,
                now,
            ),
        )
    return get_conflict(conflict_id) or {}


def list_conflicts(patient_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM conflicts WHERE patient_id = ? ORDER BY created_at", (patient_id,)
        ).fetchall()
    result = [row_to_dict(row) for row in rows]
    # Inject conflict_id alias: DB column is "id" but Pydantic schema requires "conflict_id".
    for item in result:
        item.setdefault("conflict_id", item["id"])
    return result


def get_conflict(conflict_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM conflicts WHERE id = ?", (conflict_id,)).fetchone()
    if not row:
        return None
    result = row_to_dict(row)
    result.setdefault("conflict_id", result["id"])
    return result


def update_review(conflict_id: str, review_status: str, reviewer_note: str | None, actor: str = "reviewer") -> dict:
    conflict = get_conflict(conflict_id) or {}
    now = utc_now()
    with db() as conn:
        conn.execute(
            "UPDATE conflicts SET review_status = ?, reviewer_note = COALESCE(?, reviewer_note), updated_at = ? WHERE id = ?",
            (review_status, reviewer_note, now, conflict_id),
        )
        conn.execute(
            "INSERT INTO conflict_reviews (id, conflict_id, review_status, reviewer_note, created_at) VALUES (?, ?, ?, ?, ?)",
            (new_id("rev"), conflict_id, review_status, reviewer_note, now),
        )
    log_audit(conflict.get("patient_id"), actor, "CONFLICT_REVIEW_UPDATED", {"conflict_id": conflict_id, "review_status": review_status})
    return get_conflict(conflict_id) or {}


def update_conflict_verification(
    conflict_id: str,
    verification_status: str,
    verification_reason: str | None = None,
    requires_human_review: bool = True,
    verified_at: str | None = None,
) -> dict:
    """Record the Evidence Verification Agent's decision for one conflict."""
    if verified_at is None:
        verified_at = utc_now()
    with db() as conn:
        conn.execute(
            """UPDATE conflicts
               SET verification_status = ?, verification_reason = ?, requires_human_review = ?,
                   verified_at = ?, updated_at = ?
               WHERE id = ?""",
            (verification_status, verification_reason, 1 if requires_human_review else 0, verified_at, utc_now(), conflict_id),
        )
    return get_conflict(conflict_id) or {}


# ------------------------------------------------------------- summaries

def save_summary(patient_id: str, summary: str, sections: dict, uncertainty_notes: list[str], analysis_run_id: str | None = None, data_origin: str = "USER_UPLOAD") -> dict:
    summary_id = new_id("sum")
    with db() as conn:
        conn.execute(
            """INSERT INTO patient_summaries
               (id, patient_id, analysis_run_id, summary, sections, uncertainty_notes, data_origin, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (summary_id, patient_id, analysis_run_id, summary, _dump(sections), _dump(uncertainty_notes), data_origin, utc_now()),
        )
    return get_latest_summary(patient_id) or {}


def get_latest_summary(patient_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM patient_summaries WHERE patient_id = ? ORDER BY created_at DESC LIMIT 1",
            (patient_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


# --------------------------------------------------------- analysis runs

def create_run(patient_id: str, document_ids: list[str], engine: str) -> dict:
    run_id = new_id("run")
    with db() as conn:
        conn.execute(
            """INSERT INTO analysis_runs (id, patient_id, status, engine, document_ids, started_at)
               VALUES (?, ?, 'QUEUED', ?, ?, ?)""",
            (run_id, patient_id, engine, _dump(document_ids), utc_now()),
        )
    return get_run(run_id) or {}


def update_run(run_id: str, **fields: Any) -> None:
    if not fields:
        return
    prepared: dict[str, Any] = {}
    for key, value in fields.items():
        if key in ("document_ids", "warnings", "metrics"):
            prepared[key] = _dump(value)
        else:
            prepared[key] = value
    assignments = ", ".join(f"{key} = ?" for key in prepared)
    values = list(prepared.values())
    values.append(run_id)
    with db() as conn:
        conn.execute(f"UPDATE analysis_runs SET {assignments} WHERE id = ?", values)


def get_run(run_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_runs(patient_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM analysis_runs WHERE patient_id = ? ORDER BY started_at DESC", (patient_id,)
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def add_activity(
    run_id: str,
    agent_name: str,
    activity_type: str,
    message: str,
    status: str = "RUNNING",
    tool_name: str | None = None,
    detail: dict | None = None,
) -> dict:
    activity_id = new_id("act")
    with db() as conn:
        conn.execute(
            """INSERT INTO agent_activity
               (id, analysis_run_id, agent_name, activity_type, activity_message, status, tool_name, detail, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (activity_id, run_id, agent_name, activity_type, message, status, tool_name, _dump(detail or {}), utc_now()),
        )
    return {"id": activity_id, "agent_name": agent_name, "activity_type": activity_type, "activity_message": message, "status": status, "tool_name": tool_name, "detail": detail or {}}


def list_activity(run_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_activity WHERE analysis_run_id = ? ORDER BY created_at, rowid", (run_id,)
        ).fetchall()
    return [row_to_dict(row) for row in rows]


# -------------------------------------------------------------- audit log

def log_audit(patient_id: str | None, actor: str, action: str, detail: dict | None = None) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO audit_log (id, patient_id, actor, action, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (new_id("aud"), patient_id, actor, action, _dump(detail or {}), utc_now()),
        )


def list_audit(patient_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE patient_id = ? ORDER BY created_at DESC", (patient_id,)
        ).fetchall()
    return [row_to_dict(row) for row in rows]


# --------------------------------------------------------------- datasets

def upsert_dataset_source(
    name: str,
    title: str,
    source_url: str,
    dataset_type: str,
    description: str,
    version: str | None = None,
    licence: str | None = None,
) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM dataset_sources WHERE name = ?", (name,)).fetchone()
        if row:
            conn.execute(
                "UPDATE dataset_sources SET title = ?, source_url = ?, dataset_type = ?, description = ?, version = COALESCE(?, version), licence = COALESCE(?, licence) WHERE name = ?",
                (title, source_url, dataset_type, description, version, licence, name),
            )
            source_id = row["id"]
        else:
            source_id = new_id("ds")
            conn.execute(
                """INSERT INTO dataset_sources
                   (id, name, title, source_url, version, licence, dataset_type, description, import_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NOT_IMPORTED')""",
                (source_id, name, title, source_url, version, licence, dataset_type, description),
            )
        row = conn.execute("SELECT * FROM dataset_sources WHERE id = ?", (source_id,)).fetchone()
    return row_to_dict(row)


def list_dataset_sources() -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM dataset_sources ORDER BY name").fetchall()
    return [row_to_dict(row) for row in rows]


def get_dataset_source(name: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM dataset_sources WHERE name = ? OR id = ?", (name, name)).fetchone()
    return row_to_dict(row) if row else None


def start_import_run(dataset_source_id: str) -> str:
    run_id = new_id("imp")
    with db() as conn:
        conn.execute(
            "INSERT INTO dataset_import_runs (id, dataset_source_id, status, started_at) VALUES (?, ?, 'RUNNING', ?)",
            (run_id, dataset_source_id, utc_now()),
        )
        conn.execute(
            "UPDATE dataset_sources SET import_status = 'IMPORTING' WHERE id = ?", (dataset_source_id,)
        )
    return run_id


def finish_import_run(
    run_id: str,
    dataset_source_id: str,
    status: str,
    processed: int,
    failed: int,
    errors: list[str],
) -> None:
    now = utc_now()
    with db() as conn:
        conn.execute(
            "UPDATE dataset_import_runs SET status = ?, records_processed = ?, records_failed = ?, completed_at = ?, error_details = ? WHERE id = ?",
            (status, processed, failed, now, _dump(errors), run_id),
        )
        conn.execute(
            "UPDATE dataset_sources SET import_status = ?, imported_at = ? WHERE id = ?",
            (status, now, dataset_source_id),
        )


def get_import_runs(dataset_source_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM dataset_import_runs WHERE dataset_source_id = ? ORDER BY started_at DESC LIMIT 5",
            (dataset_source_id,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def save_dataset_record(
    dataset_source_id: str,
    source_record_id: str,
    record_type: str,
    synthetic_patient_id: str | None,
    original_format: str,
    original_location: str,
    data_origin: str,
    metadata: dict,
    payload: dict,
) -> None:
    with db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO dataset_records
               (id, dataset_source_id, source_record_id, synthetic_patient_id, record_type,
                original_format, original_location, data_origin, metadata, payload, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id("drec"),
                dataset_source_id,
                source_record_id,
                synthetic_patient_id,
                record_type,
                original_format,
                original_location,
                data_origin,
                _dump(metadata),
                _dump(payload),
                utc_now(),
            ),
        )


def list_dataset_records(
    dataset_source_id: str,
    record_type: str | None = None,
    synthetic_patient_id: str | None = None,
    limit: int = 500,
) -> list[dict]:
    query = "SELECT * FROM dataset_records WHERE dataset_source_id = ?"
    params: list[Any] = [dataset_source_id]
    if record_type:
        query += " AND record_type = ?"
        params.append(record_type)
    if synthetic_patient_id:
        query += " AND synthetic_patient_id = ?"
        params.append(synthetic_patient_id)
    query += " ORDER BY source_record_id LIMIT ?"
    params.append(limit)
    with db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(row) for row in rows]


def get_dataset_record(record_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM dataset_records WHERE id = ?", (record_id,)).fetchone()
    return row_to_dict(row) if row else None


def count_dataset_records(dataset_source_id: str) -> dict[str, int]:
    with db() as conn:
        rows = conn.execute(
            "SELECT record_type, COUNT(*) AS total FROM dataset_records WHERE dataset_source_id = ? GROUP BY record_type",
            (dataset_source_id,),
        ).fetchall()
    return {row["record_type"]: row["total"] for row in rows}


def save_evaluation(
    dataset_source_id: str,
    record_id: str | None,
    agent_name: str,
    evaluation_type: str,
    generated_output: dict,
    reference_output: dict,
    score: float | None,
    details: dict,
) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO dataset_evaluations
               (id, dataset_source_id, record_id, agent_name, evaluation_type, generated_output,
                reference_output, evaluation_score, evaluation_details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id("evl"),
                dataset_source_id,
                record_id,
                agent_name,
                evaluation_type,
                _dump(generated_output),
                _dump(reference_output),
                score,
                _dump(details),
                utc_now(),
            ),
        )


def list_evaluations(dataset_source_id: str, evaluation_type: str | None = None, limit: int = 200) -> list[dict]:
    query = "SELECT * FROM dataset_evaluations WHERE dataset_source_id = ?"
    params: list[Any] = [dataset_source_id]
    if evaluation_type:
        query += " AND evaluation_type = ?"
        params.append(evaluation_type)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(row) for row in rows]

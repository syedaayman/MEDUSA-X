"""SQLite persistence layer for MEDUSA-X.

The prototype uses SQLite by default so the whole workflow survives a restart
without external credentials. Supabase remains an optional future store; the
repository functions below are the single access path so it can be swapped.
"""

from __future__ import annotations

import contextlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from backend.config import settings

SCHEMA_VERSION = 1


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with second precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    """Return a readable, collision-resistant identifier."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _prepare_dirs() -> None:
    Path(settings.database_file).parent.mkdir(parents=True, exist_ok=True)
    settings.storage_path.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    """Open a configured SQLite connection."""
    _prepare_dirs()
    conn = sqlite3.connect(str(settings.database_file), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextlib.contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """Transactional connection context manager."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    display_name TEXT,
    data_origin TEXT NOT NULL DEFAULT 'USER_UPLOAD',
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    document_type TEXT,
    document_date TEXT,
    date_precision TEXT,
    page_count INTEGER NOT NULL DEFAULT 0,
    processing_status TEXT NOT NULL DEFAULT 'UPLOADED',
    extraction_quality REAL,
    ocr_required_pages TEXT NOT NULL DEFAULT '[]',
    storage_path TEXT,
    data_origin TEXT NOT NULL DEFAULT 'USER_UPLOAD',
    created_at TEXT NOT NULL,
    UNIQUE (patient_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_documents_patient ON documents(patient_id);

CREATE TABLE IF NOT EXISTS document_pages (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    char_count INTEGER NOT NULL DEFAULT 0,
    ocr_required INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (document_id, page_number)
);

CREATE TABLE IF NOT EXISTS clinical_entities (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    original_value TEXT,
    normalized_value TEXT,
    clinical_date TEXT,
    date_precision TEXT,
    source_type TEXT NOT NULL DEFAULT 'DOCUMENT',
    source_record_id TEXT,
    source_page INTEGER,
    evidence_snippet TEXT,
    confidence REAL,
    verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
    data_origin TEXT NOT NULL DEFAULT 'USER_UPLOAD',
    attributes TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_patient ON clinical_entities(patient_id, category);
CREATE INDEX IF NOT EXISTS idx_entities_document ON clinical_entities(document_id);

CREATE TABLE IF NOT EXISTS timeline_events (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    event_date TEXT,
    date_precision TEXT,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    related_entity_ids TEXT NOT NULL DEFAULT '[]',
    source_document_id TEXT,
    source_document_name TEXT,
    source_page INTEGER,
    evidence_snippet TEXT,
    verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
    data_origin TEXT NOT NULL DEFAULT 'USER_UPLOAD',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_timeline_patient ON timeline_events(patient_id, event_date);

CREATE TABLE IF NOT EXISTS conflicts (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    analysis_run_id TEXT,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    compared_entity_ids TEXT NOT NULL DEFAULT '[]',
    compared_values TEXT NOT NULL DEFAULT '[]',
    source_references TEXT NOT NULL DEFAULT '[]',
    reason TEXT,
    possible_explanation TEXT,
    severity TEXT NOT NULL DEFAULT 'MEDIUM',
    confidence REAL,
    verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
    verification_reason TEXT,
    review_status TEXT NOT NULL DEFAULT 'PENDING',
    reviewer_note TEXT,
    requires_human_review INTEGER NOT NULL DEFAULT 1,
    data_origin TEXT NOT NULL DEFAULT 'USER_UPLOAD',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conflicts_patient ON conflicts(patient_id);

CREATE TABLE IF NOT EXISTS conflict_reviews (
    id TEXT PRIMARY KEY,
    conflict_id TEXT NOT NULL REFERENCES conflicts(id) ON DELETE CASCADE,
    review_status TEXT NOT NULL,
    reviewer_note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patient_summaries (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    analysis_run_id TEXT,
    summary TEXT NOT NULL,
    sections TEXT NOT NULL DEFAULT '{}',
    uncertainty_notes TEXT NOT NULL DEFAULT '[]',
    data_origin TEXT NOT NULL DEFAULT 'USER_UPLOAD',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_summaries_patient ON patient_summaries(patient_id, created_at);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    current_agent TEXT,
    engine TEXT NOT NULL DEFAULT 'agents_sdk',
    document_ids TEXT NOT NULL DEFAULT '[]',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_message TEXT,
    warnings TEXT NOT NULL DEFAULT '[]',
    metrics TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_runs_patient ON analysis_runs(patient_id, started_at);

CREATE TABLE IF NOT EXISTS agent_activity (
    id TEXT PRIMARY KEY,
    analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    activity_message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    tool_name TEXT,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_run ON agent_activity(analysis_run_id, created_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    patient_id TEXT,
    actor TEXT NOT NULL DEFAULT 'agent',
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    title TEXT,
    source_url TEXT,
    version TEXT,
    licence TEXT,
    dataset_type TEXT,
    description TEXT,
    imported_at TEXT,
    import_status TEXT NOT NULL DEFAULT 'NOT_IMPORTED'
);

CREATE TABLE IF NOT EXISTS dataset_import_runs (
    id TEXT PRIMARY KEY,
    dataset_source_id TEXT NOT NULL REFERENCES dataset_sources(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    records_processed INTEGER NOT NULL DEFAULT 0,
    records_failed INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_details TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_import_runs_source ON dataset_import_runs(dataset_source_id, started_at);

CREATE TABLE IF NOT EXISTS dataset_records (
    id TEXT PRIMARY KEY,
    dataset_source_id TEXT NOT NULL REFERENCES dataset_sources(id) ON DELETE CASCADE,
    source_record_id TEXT NOT NULL,
    synthetic_patient_id TEXT,
    record_type TEXT NOT NULL,
    original_format TEXT,
    original_location TEXT,
    data_origin TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    payload TEXT NOT NULL DEFAULT '{}',
    imported_at TEXT NOT NULL,
    UNIQUE (dataset_source_id, source_record_id, record_type)
);
CREATE INDEX IF NOT EXISTS idx_dataset_records_patient ON dataset_records(synthetic_patient_id);

CREATE TABLE IF NOT EXISTS dataset_evaluations (
    id TEXT PRIMARY KEY,
    dataset_source_id TEXT NOT NULL REFERENCES dataset_sources(id) ON DELETE CASCADE,
    record_id TEXT,
    agent_name TEXT NOT NULL,
    evaluation_type TEXT NOT NULL,
    generated_output TEXT NOT NULL DEFAULT '{}',
    reference_output TEXT NOT NULL DEFAULT '{}',
    evaluation_score REAL,
    evaluation_details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_source ON dataset_evaluations(dataset_source_id, evaluation_type);
"""


def init_db() -> None:
    """Create tables when missing. Safe to call repeatedly."""
    with db() as conn:
        conn.executescript(SCHEMA)


def reset_db() -> None:
    """Drop all application data (used by tests only)."""
    tables = [
        "agent_activity",
        "analysis_runs",
        "conflict_reviews",
        "conflicts",
        "patient_summaries",
        "timeline_events",
        "clinical_entities",
        "document_pages",
        "documents",
        "audit_log",
        "dataset_evaluations",
        "dataset_records",
        "dataset_import_runs",
        "dataset_sources",
        "patients",
    ]
    with db() as conn:
        for table in tables:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
    init_db()

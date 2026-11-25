"""Common clinical schema shared by uploads, Synthea and EkaCare data.

Every entity keeps both the original wording and a normalized value, plus an
explicit source reference. Unknown values stay ``None`` and are never inferred.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DataOrigin(str, Enum):
    USER_UPLOAD = "USER_UPLOAD"
    SYNTHETIC_DATASET = "SYNTHETIC_DATASET"
    EKACARE_EVALUATION = "EKACARE_EVALUATION"
    CONTROLLED_TEST_FIXTURE = "CONTROLLED_TEST_FIXTURE"


class VerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SUPPORTED = "SUPPORTED"
    VERIFIED_POTENTIAL_CONFLICT = "VERIFIED_POTENTIAL_CONFLICT"
    NOT_A_CONFLICT = "NOT_A_CONFLICT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    REVIEWED = "REVIEWED"
    UNRESOLVED = "UNRESOLVED"
    DISMISSED = "DISMISSED"


class AgentStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    SKIPPED = "SKIPPED"


class DatePrecision(str, Enum):
    DAY = "DAY"
    MONTH = "MONTH"
    YEAR = "YEAR"
    UNKNOWN = "UNKNOWN"


class EntityCategory(str, Enum):
    DIAGNOSIS = "DIAGNOSIS"
    SYMPTOM = "SYMPTOM"
    MEDICATION = "MEDICATION"
    ALLERGY = "ALLERGY"
    PROCEDURE = "PROCEDURE"
    LAB = "LAB"
    VITAL = "VITAL"
    PLAN = "PLAN"


class ClinicalEntity(BaseModel):
    """A single extracted clinical fact with full provenance."""

    id: str
    patient_id: str
    category: EntityCategory
    original_value: str | None = None
    normalized_value: str | None = None
    clinical_date: str | None = None
    date_precision: DatePrecision = DatePrecision.UNKNOWN
    source_type: str = "DOCUMENT"
    source_document_id: str | None = None
    source_document_name: str | None = None
    source_record_id: str | None = None
    source_page: int | None = None
    evidence_snippet: str | None = None
    confidence: float | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    data_origin: DataOrigin = DataOrigin.USER_UPLOAD
    attributes: dict[str, Any] = Field(default_factory=dict)


class MedicationAttributes(BaseModel):
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = None
    duration: str | None = None
    status: str | None = None


class LabAttributes(BaseModel):
    value: str | None = None
    unit: str | None = None
    reference_range: str | None = None


class DocumentAnalysis(BaseModel):
    """Document Intelligence Agent output."""

    document_id: str
    filename: str
    document_type: str
    document_date: str | None = None
    date_precision: DatePrecision = DatePrecision.UNKNOWN
    page_count: int
    relevant_pages: list[int] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    extraction_quality: float = 0.0
    missing_information: list[str] = Field(default_factory=list)
    ocr_required_pages: list[int] = Field(default_factory=list)
    processing_status: str = "COMPLETED"


class TimelineEvent(BaseModel):
    event_id: str
    patient_id: str
    event_date: str | None = None
    date_precision: DatePrecision = DatePrecision.UNKNOWN
    category: str
    description: str
    related_entity_ids: list[str] = Field(default_factory=list)
    source_document_id: str | None = None
    source_document_name: str | None = None
    source_page: int | None = None
    evidence_snippet: str | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    data_origin: DataOrigin = DataOrigin.USER_UPLOAD


class SourceReference(BaseModel):
    document_id: str
    document_name: str | None = None
    page: int | None = None
    snippet: str | None = None
    clinical_date: str | None = None


class ConflictProposal(BaseModel):
    """Reconciliation Agent output before verification."""

    conflict_id: str
    category: str
    description: str
    compared_entity_ids: list[str]
    compared_values: list[str]
    source_references: list[SourceReference]
    reason: str
    possible_explanation: str | None = None
    severity: str = "MEDIUM"
    confidence: float | None = None
    requires_human_review: bool = True


class VerificationDecision(BaseModel):
    """Evidence Verification Agent output."""

    conflict_id: str
    decision: VerificationStatus
    reason: str
    checked_sources: list[SourceReference] = Field(default_factory=list)
    temporal_change_explained: bool = False


class PatientSummary(BaseModel):
    patient_id: str
    summary: str
    sections: dict[str, Any] = Field(default_factory=dict)
    uncertainty_notes: list[str] = Field(default_factory=list)
    data_origin: DataOrigin = DataOrigin.USER_UPLOAD


class PatientContext(BaseModel):
    patient_id: str
    display_name: str | None = None
    data_origin: DataOrigin = DataOrigin.USER_UPLOAD
    document_count: int = 0
    entity_count: int = 0
    documents: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)


class DatasetSourceInfo(BaseModel):
    id: str
    name: str
    title: str | None = None
    source_url: str | None = None
    version: str | None = None
    licence: str | None = None
    dataset_type: str | None = None
    description: str | None = None
    imported_at: str | None = None
    import_status: str = "NOT_IMPORTED"


class EvaluationMetrics(BaseModel):
    """Reproducible, count-based metrics. Never estimated."""

    samples: int = 0
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    exact_match: float | None = None
    missing_field_rate: float | None = None
    unsupported_entity_rate: float | None = None
    notes: list[str] = Field(default_factory=list)

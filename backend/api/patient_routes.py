"""Patient, document, timeline and conflict API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend import repository
from backend.schemas import (
    ClinicalEntity,
    ConflictProposal,
    DocumentPage,
    Patient,
    TimelineEvent,
    UploadedDocument,
)

router = APIRouter(tags=["patient"])

REVIEW_STATUSES = {"PENDING", "REVIEWED", "UNRESOLVED", "DISMISSED"}


class ReviewUpdate(BaseModel):
    review_status: str = Field(..., description="PENDING | REVIEWED | UNRESOLVED | DISMISSED")
    reviewer_note: str | None = Field(default=None, max_length=2000)
    actor: str = Field(default="reviewer", max_length=120)


@router.get("/api/patient/{patient_id}", response_model=Patient)
def get_patient(patient_id: str) -> Patient:
    patient = repository.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return Patient.model_validate(patient)


@router.get("/api/patient/{patient_id}/documents", response_model=list[UploadedDocument])
def list_documents(patient_id: str) -> list[UploadedDocument]:
    if not repository.get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return [UploadedDocument.model_validate(doc) for doc in repository.list_documents(patient_id)]


@router.get("/api/documents/{document_id}", response_model=UploadedDocument)
def get_document(document_id: str) -> UploadedDocument:
    document = repository.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return UploadedDocument.model_validate(document)


@router.get("/api/documents/{document_id}/pages/{page_number}", response_model=DocumentPage)
def get_document_page(document_id: str, page_number: int) -> DocumentPage:
    if not repository.get_document(document_id):
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    page = repository.get_page(document_id, page_number)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page {page_number} not found in document {document_id}")
    return DocumentPage.model_validate(page)


@router.get("/api/patient/{patient_id}/entities", response_model=list[ClinicalEntity])
def list_entities(
    patient_id: str,
    categories: str | None = Query(default=None, description="Comma-separated category filter"),
) -> list[ClinicalEntity]:
    if not repository.get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    category_list = [item.strip().upper() for item in (categories or "").split(",") if item.strip()]
    return [
        ClinicalEntity.model_validate(entity)
        for entity in repository.list_entities(patient_id, categories=category_list or None)
    ]


@router.get("/api/patient/{patient_id}/timeline", response_model=list[TimelineEvent])
def get_timeline(patient_id: str) -> list[TimelineEvent]:
    if not repository.get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return [TimelineEvent.model_validate(event) for event in repository.list_timeline(patient_id)]


@router.get("/api/patient/{patient_id}/conflicts", response_model=list[ConflictProposal])
def get_conflicts(
    patient_id: str,
    review_status: str | None = Query(default=None),
) -> list[ConflictProposal]:
    if not repository.get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    conflicts = repository.list_conflicts(patient_id)
    if review_status:
        conflicts = [item for item in conflicts if item.get("review_status") == review_status.upper()]
    return [ConflictProposal.model_validate(item) for item in conflicts]


@router.get("/api/conflicts/{conflict_id}", response_model=ConflictProposal)
def get_conflict(conflict_id: str) -> ConflictProposal:
    conflict = repository.get_conflict(conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail=f"Conflict {conflict_id} not found")
    return ConflictProposal.model_validate(conflict)


@router.patch("/api/conflicts/{conflict_id}/review", response_model=ConflictProposal)
def update_conflict_review(conflict_id: str, payload: ReviewUpdate) -> ConflictProposal:
    """Persist a reviewer decision and keep the audit trail."""
    if not repository.get_conflict(conflict_id):
        raise HTTPException(status_code=404, detail=f"Conflict {conflict_id} not found")
    status = payload.review_status.upper()
    if status not in REVIEW_STATUSES:
        raise HTTPException(status_code=422, detail=f"review_status must be one of {sorted(REVIEW_STATUSES)}")
    updated = repository.update_review(conflict_id, status, payload.reviewer_note, actor=payload.actor)
    return ConflictProposal.model_validate(updated)


@router.get("/api/patient/{patient_id}/audit")
def get_audit_trail(patient_id: str, limit: int = Query(default=100, ge=1, le=500)) -> dict:
    if not repository.get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return {"patient_id": patient_id, "entries": repository.list_audit(patient_id)[:limit]}

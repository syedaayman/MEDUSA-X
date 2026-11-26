"""Summary and evidence API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend import repository
from backend.clinical.summary_builder import build_summary

router = APIRouter(tags=["summary"])


@router.get("/api/patient/{patient_id}/summary")
def get_patient_summary(patient_id: str) -> dict:
    """Return the stored summary, rebuilding it from stored evidence if absent."""
    if not repository.get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    stored = repository.get_latest_summary(patient_id)
    if stored:
        return {"patient_id": patient_id, "stored": True, **stored}
    if not repository.list_entities(patient_id):
        raise HTTPException(
            status_code=404,
            detail="No summary yet. Run an analysis after uploading documents.",
        )
    return {"patient_id": patient_id, "stored": False, **build_summary(patient_id)}


@router.get("/api/conflicts/{conflict_id}/evidence")
def get_conflict_evidence(conflict_id: str) -> dict:
    """Return the original page text behind every compared value of a finding."""
    conflict = repository.get_conflict(conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail=f"Conflict {conflict_id} not found")

    references: list[dict] = []
    for entity_id in conflict.get("compared_entity_ids") or []:
        entity = repository.get_entity(entity_id) if hasattr(repository, "get_entity") else None
        if not entity:
            references.append(
                {
                    "entity_id": entity_id,
                    "available": False,
                    "reason": "Entity is no longer stored; the original evidence cannot be re-read.",
                }
            )
            continue
        page = (
            repository.get_page(entity["document_id"], entity["source_page"])
            if entity.get("document_id") and entity.get("source_page")
            else None
        )
        references.append(
            {
                "entity_id": entity_id,
                "available": page is not None,
                "category": entity.get("category"),
                "value": entity.get("normalized_value") or entity.get("original_value"),
                "original_value": entity.get("original_value"),
                "clinical_date": entity.get("clinical_date"),
                "document_id": entity.get("document_id"),
                "filename": entity.get("source_filename") or (repository.get_document(entity["document_id"]) or {}).get("filename"),
                "page": entity.get("source_page"),
                "snippet": entity.get("evidence_snippet"),
                "page_text": (page or {}).get("text"),
                "ocr_required": (page or {}).get("ocr_required"),
                "verification_status": entity.get("verification_status"),
            }
        )

    return {
        "conflict_id": conflict_id,
        "category": conflict.get("category"),
        "description": conflict.get("description"),
        "verification_status": conflict.get("verification_status"),
        "verification_reason": conflict.get("verification_reason"),
        "review_status": conflict.get("review_status"),
        "references": references,
        "stored_source_references": conflict.get("source_references") or [],
    }


@router.get("/api/events/{event_id}/evidence")
def get_event_evidence(event_id: str) -> dict:
    """Return the source page for one timeline event."""
    event = repository.get_event(event_id) if hasattr(repository, "get_event") else None
    if not event:
        raise HTTPException(status_code=404, detail=f"Timeline event {event_id} not found")
    page = (
        repository.get_page(event["document_id"], event["source_page"])
        if event.get("document_id") and event.get("source_page")
        else None
    )
    return {
        "event_id": event_id,
        "description": event.get("description"),
        "event_date": event.get("event_date"),
        "date_precision": event.get("date_precision"),
        "document_id": event.get("document_id"),
        "filename": (repository.get_document(event["document_id"]) or {}).get("filename"),
        "page": event.get("source_page"),
        "snippet": event.get("supporting_text"),
        "page_text": (page or {}).get("text"),
        "ocr_required": (page or {}).get("ocr_required"),
        "verification_status": event.get("verification_status"),
    }

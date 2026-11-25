"""Evidence-backed patient summary generation.

The summary restates only what the stored entities and verified discrepancies
contain. It never recommends treatment, never resolves a discrepancy and always
keeps the medical-review disclaimer.
"""

from __future__ import annotations

from typing import Any

from backend import repository
from backend.clinical.timeline_builder import describe_changes, describe_entity

DISCLAIMER = (
    "MEDUSA-X is a research prototype. This summary is generated from extracted document text and may "
    "omit or misread information. It is not a diagnosis, not treatment advice and does not replace "
    "review of the original records by a qualified clinician."
)

STATUS_LABEL = {
    "ACTIVE": "current",
    "DISCONTINUED": "historical (documented as discontinued)",
    "HISTORICAL": "historical",
    "COMPLETED": "completed",
    "UNKNOWN": "status not stated in the source",
}


def _group(entities: list[dict], category: str) -> list[dict]:
    return [entity for entity in entities if entity.get("category") == category]


def _line(entity: dict) -> str:
    source = []
    if entity.get("source_page"):
        source.append(f"page {entity['source_page']}")
    if entity.get("clinical_date"):
        source.append(entity["clinical_date"])
    suffix = f" [{', '.join(source)}]" if source else ""
    return f"{describe_entity(entity)}{suffix}"


def build_summary(
    patient_id: str,
    entities: list[dict] | None = None,
    conflicts: list[dict] | None = None,
    documents: list[dict] | None = None,
) -> dict[str, Any]:
    """Compose a structured, provenance-preserving summary."""
    entities = entities if entities is not None else repository.list_entities(patient_id)
    conflicts = conflicts if conflicts is not None else repository.list_conflicts(patient_id)
    documents = documents if documents is not None else repository.list_documents(patient_id)
    patient = repository.get_patient(patient_id) or {}

    diagnoses = _group(entities, "DIAGNOSIS")
    symptoms = _group(entities, "SYMPTOM")
    medications = _group(entities, "MEDICATION")
    allergies = _group(entities, "ALLERGY")
    procedures = _group(entities, "PROCEDURE")
    labs = _group(entities, "LAB")
    vitals = _group(entities, "VITAL")
    plans = _group(entities, "PLAN")

    uncertainty: list[str] = []
    ocr_documents = [doc["filename"] for doc in documents if (doc.get("processing_status") or "") == "OCR_REQUIRED"]
    if ocr_documents:
        uncertainty.append(
            "Pages without extractable text were found in: " + ", ".join(sorted(set(ocr_documents)))
            + ". Those pages are marked OCR_REQUIRED and their content is not represented here."
        )
    undated = [entity for entity in entities if not entity.get("clinical_date")]
    if undated:
        uncertainty.append(
            f"{len(undated)} extracted item(s) have no clinical date in the source text and are listed without a date."
        )
    unknown_status = [entity for entity in medications if (entity.get("attributes") or {}).get("status") in (None, "", "UNKNOWN")]
    if unknown_status:
        uncertainty.append(
            f"{len(unknown_status)} medication entr(y/ies) do not state whether the medication is current or historical."
        )

    pending = [conflict for conflict in conflicts if conflict.get("review_status") == "PENDING"]
    insufficient = [conflict for conflict in conflicts if conflict.get("verification_status") == "INSUFFICIENT_EVIDENCE"]

    sections: dict[str, Any] = {
        "overview": {
            "patient_id": patient_id,
            "display_name": patient.get("display_name"),
            "data_origin": patient.get("data_origin") or "USER_UPLOAD",
            "document_count": len(documents),
            "documents": [
                {
                    "id": doc.get("id"),
                    "filename": doc.get("filename"),
                    "document_type": doc.get("document_type"),
                    "document_date": doc.get("document_date"),
                    "page_count": doc.get("page_count"),
                    "processing_status": doc.get("processing_status"),
                }
                for doc in documents
            ],
        },
        "current_medications": [
            _line(entity) for entity in medications if (entity.get("attributes") or {}).get("status") == "ACTIVE"
        ],
        "historical_medications": [
            _line(entity)
            for entity in medications
            if (entity.get("attributes") or {}).get("status") in ("HISTORICAL", "DISCONTINUED", "COMPLETED")
        ],
        "medications_status_unclear": [
            _line(entity)
            for entity in medications
            if (entity.get("attributes") or {}).get("status") in (None, "", "UNKNOWN")
        ],
        "diagnoses": [_line(entity) for entity in diagnoses],
        "symptoms": [_line(entity) for entity in symptoms],
        "allergies": [_line(entity) for entity in allergies],
        "procedures": [_line(entity) for entity in procedures],
        "laboratory_results": [_line(entity) for entity in labs],
        "vital_signs": [_line(entity) for entity in vitals],
        "plans": [_line(entity) for entity in plans],
        "changes_over_time": describe_changes(repository.list_timeline(patient_id)),
        "potential_discrepancies": [
            {
                "id": conflict.get("id"),
                "category": conflict.get("category"),
                "description": conflict.get("description"),
                "verification_status": conflict.get("verification_status"),
                "review_status": conflict.get("review_status"),
                "severity": conflict.get("severity"),
            }
            for conflict in conflicts
        ],
        "counts": {
            "entities": len(entities),
            "timeline_events": len(repository.list_timeline(patient_id)),
            "conflicts": len(conflicts),
            "pending_review": len(pending),
        },
    }

    if insufficient:
        uncertainty.append(
            f"{len(insufficient)} proposed discrepancy(ies) could not be supported by the stored evidence and are marked INSUFFICIENT_EVIDENCE."
        )
    if not documents:
        uncertainty.append("No documents are stored for this patient yet.")

    text_parts: list[str] = []
    header = patient.get("display_name") or patient_id
    text_parts.append(
        f"Patient {header} ({patient_id}). {len(documents)} document(s) analysed, {len(entities)} clinical item(s) extracted."
    )
    if sections["current_medications"]:
        text_parts.append("Current medications: " + "; ".join(sections["current_medications"]) + ".")
    if sections["historical_medications"]:
        text_parts.append("Historical medications: " + "; ".join(sections["historical_medications"]) + ".")
    if sections["medications_status_unclear"]:
        text_parts.append(
            "Medications with unclear status: " + "; ".join(sections["medications_status_unclear"]) + "."
        )
    if sections["diagnoses"]:
        text_parts.append("Documented diagnoses: " + "; ".join(sections["diagnoses"]) + ".")
    if sections["allergies"]:
        text_parts.append("Recorded allergies: " + "; ".join(sections["allergies"]) + ".")
    if sections["procedures"]:
        text_parts.append("Procedures: " + "; ".join(sections["procedures"]) + ".")
    if sections["laboratory_results"]:
        text_parts.append("Laboratory results: " + "; ".join(sections["laboratory_results"]) + ".")
    if conflicts:
        text_parts.append(
            f"{len(conflicts)} potential discrepancy(ies) were proposed; "
            f"{len(pending)} still require human review."
        )
    else:
        text_parts.append("No cross-document discrepancies were proposed from the comparable records.")
    text_parts.append(DISCLAIMER)

    return {
        "patient_id": patient_id,
        "summary": " ".join(text_parts),
        "sections": sections,
        "uncertainty_notes": uncertainty,
    }

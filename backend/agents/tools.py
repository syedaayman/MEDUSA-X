"""Real tool functions shared by the agents and the API.

Every tool validates its input, enforces patient-level isolation and records its
execution so the frontend shows genuine agent activity rather than animation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend import repository
from backend.clinical import entity_extractor, reconcilers, summary_builder, timeline_builder, verifier
from backend.config import settings
from backend.ingestion import document_classifier


class ToolError(ValueError):
    """Raised when a tool cannot execute on the given inputs."""


@dataclass
class ToolContext:
    """Per-run context: which patient, which run, which agent is acting."""

    run_id: str
    patient_id: str
    agent: str = "ORCHESTRATOR"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def as_agent(self, name: str) -> "ToolContext":
        return ToolContext(run_id=self.run_id, patient_id=self.patient_id, agent=name, calls=self.calls)

    def record(self, tool: str, summary: str, status: str = "COMPLETED", detail: dict | None = None) -> None:
        entry = {"tool": tool, "summary": summary, "status": status, "detail": detail or {}}
        self.calls.append(entry)
        repository.add_activity(
            self.run_id,
            self.agent,
            "TOOL_CALL",
            f"{tool}: {summary}",
            status=status,
            tool_name=tool,
            detail=detail or {},
        )


def _document_for(ctx: ToolContext, document_id: str) -> dict:
    document = repository.get_document(document_id)
    if not document or document.get("patient_id") != ctx.patient_id:
        raise ToolError(f"document {document_id} does not belong to patient {ctx.patient_id}")
    return document


# ------------------------------------------------------------------ context
def get_patient_context(ctx: ToolContext) -> dict:
    patient = repository.get_patient(ctx.patient_id) or repository.ensure_patient(ctx.patient_id)
    documents = repository.list_documents(ctx.patient_id)
    entities = repository.list_entities(ctx.patient_id)
    context = {
        "patient_id": ctx.patient_id,
        "display_name": patient.get("display_name"),
        "data_origin": patient.get("data_origin"),
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
        "document_count": len(documents),
        "entity_count": len(entities),
        "entity_counts": entity_extractor.entity_summary(entities),
        "conflict_count": len(repository.list_conflicts(ctx.patient_id)),
    }
    ctx.record("get_patient_context", f"{len(documents)} document(s), {len(entities)} entity(ies)")
    return context


def read_document(ctx: ToolContext, document_id: str) -> dict:
    document = _document_for(ctx, document_id)
    text = repository.document_text(document_id, max_chars=settings.max_document_chars_for_model)
    ctx.record("read_document", f"read {document['filename']}", detail={"document_id": document_id})
    return {
        "document_id": document_id,
        "filename": document.get("filename"),
        "page_count": document.get("page_count"),
        "processing_status": document.get("processing_status"),
        "text": text,
        "truncated": len(repository.document_text(document_id)) > len(text),
    }


def get_document_page(ctx: ToolContext, document_id: str, page_number: int) -> dict:
    _document_for(ctx, document_id)
    page = repository.get_page(document_id, int(page_number))
    if not page:
        raise ToolError(f"page {page_number} not found in document {document_id}")
    ctx.record("get_document_page", f"page {page_number}", detail={"document_id": document_id})
    return {
        "document_id": document_id,
        "page_number": page["page_number"],
        "text": page.get("text") or "",
        "ocr_required": bool(page.get("ocr_required")),
    }


def search_patient_records(ctx: ToolContext, query: str, limit: int = 10) -> dict:
    needle = (query or "").strip().lower()
    if not needle:
        raise ToolError("query must not be empty")
    matches: list[dict] = []
    for document in repository.list_documents(ctx.patient_id):
        for page in repository.list_pages(document["id"]):
            text = page.get("text") or ""
            position = text.lower().find(needle)
            if position < 0:
                continue
            start = max(0, position - 120)
            matches.append(
                {
                    "document_id": document["id"],
                    "document_name": document.get("filename"),
                    "page": page["page_number"],
                    "snippet": text[start : position + len(needle) + 120].strip(),
                }
            )
            if len(matches) >= limit:
                break
        if len(matches) >= limit:
            break
    ctx.record("search_patient_records", f"'{query}' → {len(matches)} match(es)")
    return {"query": query, "matches": matches}


# ------------------------------------------------------------- intelligence
def classify_document(ctx: ToolContext, document_id: str) -> dict:
    document = _document_for(ctx, document_id)
    pages = repository.list_pages(document_id)
    if not pages:
        raise ToolError(f"document {document_id} has no extracted pages")
    result = document_classifier.classify_text(pages)
    ocr_pages = [page["page_number"] for page in pages if page.get("ocr_required")]
    quality = entity_extractor.extraction_quality(pages, [], ocr_pages)
    repository.update_document(
        document_id,
        document_type=result.document_type,
        document_date=result.document_date,
        date_precision=result.date_precision,
        processing_status="OCR_REQUIRED" if quality == "OCR_REQUIRED" else "EXTRACTED",
        extraction_quality=1.0 if quality == "HIGH" else 0.6 if quality in ("MEDIUM", "PARTIAL") else 0.2,
    )
    ctx.record(
        "classify_document",
        f"{document['filename']} → {result.document_type}"
        + (f" dated {result.document_date}" if result.document_date else " with no labelled date"),
        detail={"document_id": document_id, "sections": result.sections},
    )
    return {
        "document_id": document_id,
        "filename": document.get("filename"),
        "document_type": result.document_type,
        "document_date": result.document_date,
        "date_precision": result.date_precision,
        "sections": result.sections,
        "relevant_pages": result.relevant_pages,
        "observations": result.observations,
        "missing_information": result.missing_information,
        "ocr_required_pages": ocr_pages,
        "extraction_quality": quality,
        "processing_status": "OCR_REQUIRED" if quality == "OCR_REQUIRED" else "COMPLETED",
    }


def extract_clinical_entities(ctx: ToolContext, document_id: str) -> dict:
    document = _document_for(ctx, document_id)
    pages = repository.list_pages(document_id)
    if not pages:
        raise ToolError(f"document {document_id} has no extracted pages")
    entities = entity_extractor.extract_entities_from_pages(pages, document, ctx.patient_id)
    stored = repository.save_entities(ctx.patient_id, entities)
    ocr_pages = [page["page_number"] for page in pages if page.get("ocr_required")]
    quality = entity_extractor.extraction_quality(pages, entities, ocr_pages)
    ctx.record(
        "extract_clinical_entities",
        f"{stored} entity(ies) from {document['filename']} (quality {quality})",
        detail={"document_id": document_id, "counts": entity_extractor.entity_summary(entities)},
    )
    return {
        "document_id": document_id,
        "stored": stored,
        "counts": entity_extractor.entity_summary(entities),
        "extraction_quality": quality,
        "ocr_required_pages": ocr_pages,
    }


def get_clinical_entities(ctx: ToolContext, category: str | None = None) -> dict:
    categories = [category] if category else None
    entities = repository.list_entities(ctx.patient_id, categories=categories)
    ctx.record("get_clinical_entities", f"{len(entities)} entity(ies) returned")
    return {"count": len(entities), "entities": entities}


# ----------------------------------------------------------- reconciliation
def compare_records(ctx: ToolContext) -> dict:
    entities = repository.list_entities(ctx.patient_id)
    documents = repository.list_documents(ctx.patient_id)
    proposals = reconcilers.propose_all(entities, documents, ctx.patient_id)
    saved: list[dict] = []
    for proposal in proposals:
        saved.append(repository.save_conflict(ctx.patient_id, proposal))
    ctx.record(
        "compare_records",
        f"{len(saved)} potential discrepancy(ies) proposed from {len(entities)} entity(ies)",
        detail={"categories": sorted({item.get('category') for item in saved})},
    )
    return {"proposed": len(saved), "conflicts": saved}


def compare_medications(ctx: ToolContext) -> dict:
    entities = repository.list_entities(ctx.patient_id)
    proposals = reconcilers.compare_medications(entities, ctx.patient_id)
    ctx.record("compare_medications", f"{len(proposals)} proposal(s)")
    return {"proposals": proposals}


def compare_diagnoses(ctx: ToolContext) -> dict:
    entities = repository.list_entities(ctx.patient_id)
    proposals = reconcilers.compare_diagnoses(entities, ctx.patient_id)
    ctx.record("compare_diagnoses", f"{len(proposals)} proposal(s)")
    return {"proposals": proposals}


def compare_allergies(ctx: ToolContext) -> dict:
    entities = repository.list_entities(ctx.patient_id)
    proposals = reconcilers.compare_allergies(entities, ctx.patient_id)
    ctx.record("compare_allergies", f"{len(proposals)} proposal(s)")
    return {"proposals": proposals}


def compare_laboratory_results(ctx: ToolContext) -> dict:
    entities = repository.list_entities(ctx.patient_id)
    proposals = reconcilers.compare_laboratory_results(entities, ctx.patient_id)
    ctx.record("compare_laboratory_results", f"{len(proposals)} proposal(s)")
    return {"proposals": proposals}


# -------------------------------------------------------------- verification
def verify_evidence(ctx: ToolContext, conflict_id: str) -> dict:
    conflict = repository.get_conflict(conflict_id)
    if not conflict or conflict.get("patient_id") != ctx.patient_id:
        raise ToolError(f"conflict {conflict_id} does not belong to patient {ctx.patient_id}")
    result = verifier.verify_conflict(ctx.patient_id, conflict)
    repository.update_conflict_verification(
        conflict_id,
        result["decision"],
        result["verification_reason"],
        requires_human_review=result["requires_human_review"],
    )
    ctx.record(
        "verify_evidence",
        f"{conflict_id} → {result['decision']}",
        detail={"checks": len(result["checks"])},
    )
    return result


def get_event_evidence(ctx: ToolContext, event_id: str) -> dict:
    event = repository.get_event(event_id)
    if not event or event.get("patient_id") != ctx.patient_id:
        raise ToolError(f"event {event_id} does not belong to patient {ctx.patient_id}")
    page = repository.get_page(event.get("source_document_id"), event.get("source_page")) if event.get("source_page") else None
    ctx.record("get_event_evidence", f"evidence for {event_id}")
    return {
        "event_id": event_id,
        "document_id": event.get("source_document_id"),
        "document_name": event.get("source_document_name"),
        "page": event.get("source_page"),
        "page_text": (page or {}).get("text"),
        "snippet": event.get("evidence_snippet"),
    }


# ------------------------------------------------------------------- writing
def save_clinical_entities(ctx: ToolContext, entities: list[dict]) -> dict:
    if not isinstance(entities, list) or not entities:
        raise ToolError("entities must be a non-empty list")
    for entity in entities:
        if entity.get("patient_id") not in (None, ctx.patient_id):
            raise ToolError("entity patient_id does not match the active patient")
        entity["patient_id"] = ctx.patient_id
        entity.setdefault("data_origin", repository.get_patient(ctx.patient_id).get("data_origin", "USER_UPLOAD"))
    stored = repository.save_entities(ctx.patient_id, entities)
    ctx.record("save_clinical_entities", f"saved {stored} entity(ies)")
    return {"stored": stored}


def save_conflict(ctx: ToolContext, conflict: dict) -> dict:
    if not conflict.get("category") or not conflict.get("description"):
        raise ToolError("conflict requires category and description")
    saved = repository.save_conflict(ctx.patient_id, conflict)
    ctx.record("save_conflict", f"saved conflict {saved.get('id')}")
    return saved


def build_patient_timeline(ctx: ToolContext) -> dict:
    events = timeline_builder.persist_timeline(ctx.patient_id)
    ctx.record("build_patient_timeline", f"{len(events)} event(s) stored")
    return {"events": events, "count": len(events)}


def generate_patient_summary(ctx: ToolContext) -> dict:
    summary = summary_builder.build_summary(ctx.patient_id)
    patient = repository.get_patient(ctx.patient_id) or {}
    repository.save_summary(
        ctx.patient_id,
        summary["summary"],
        summary["sections"],
        summary["uncertainty_notes"],
        analysis_run_id=ctx.run_id,
        data_origin=patient.get("data_origin", "USER_UPLOAD"),
    )
    ctx.record("generate_patient_summary", f"summary generated ({len(summary['uncertainty_notes'])} uncertainty note(s))")
    return summary


def request_human_review(ctx: ToolContext, conflict_id: str, reason: str = "") -> dict:
    conflict = repository.get_conflict(conflict_id)
    if not conflict or conflict.get("patient_id") != ctx.patient_id:
        raise ToolError(f"conflict {conflict_id} does not belong to patient {ctx.patient_id}")
    updated = repository.update_review(conflict_id, "PENDING", reason or "Routed to human review by the orchestrator")
    ctx.record("request_human_review", f"{conflict_id} queued for review")
    return updated


def update_review_status(ctx: ToolContext, conflict_id: str, status: str, note: str = "") -> dict:
    allowed = {"PENDING", "REVIEWED", "UNRESOLVED", "DISMISSED"}
    if status not in allowed:
        raise ToolError(f"status must be one of {sorted(allowed)}")
    conflict = repository.get_conflict(conflict_id)
    if not conflict or conflict.get("patient_id") != ctx.patient_id:
        raise ToolError(f"conflict {conflict_id} does not belong to patient {ctx.patient_id}")
    updated = repository.update_review(conflict_id, status, note or None, actor="agent")
    ctx.record("update_review_status", f"{conflict_id} → {status}")
    return updated

"""Document ingestion pipeline: validate, store, extract pages, classify."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend import repository
from backend.config import settings
from backend.ingestion import document_classifier
from backend.ingestion.pdf_reader import extract_pdf_text, looks_like_pdf


class IngestionError(ValueError):
    """Raised for a document that cannot be accepted."""


def _store_bytes(patient_id: str, filename: str, content: bytes) -> str:
    safe_name = Path(filename).name.replace("..", "_") or "document.pdf"
    target_dir = settings.storage_path / patient_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{hashlib.sha256(content).hexdigest()[:16]}_{safe_name}"
    target.write_bytes(content)
    return str(target)


def ingest_document(
    patient_id: str,
    filename: str,
    content: bytes,
    data_origin: str = "USER_UPLOAD",
    reprocess: bool = False,
) -> dict:
    """Accept one PDF and return its stored metadata and extraction status."""
    if not content:
        raise IngestionError("Uploaded file is empty")
    if len(content) > settings.max_upload_bytes:
        raise IngestionError(
            f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit"
        )
    if not looks_like_pdf(content):
        raise IngestionError("File is not a valid PDF (missing %PDF header)")

    repository.ensure_patient(patient_id)
    content_hash = hashlib.sha256(content).hexdigest()
    document, created = repository.create_document(
        patient_id=patient_id,
        filename=Path(filename).name or "document.pdf",
        content_hash=content_hash,
        storage_path=None,
        data_origin=data_origin,
    )

    if not created and not reprocess:
        return {
            "document": document,
            "duplicate": True,
            "created": False,
            "extraction": {
                "status": document.get("processing_status") or "EXTRACTED",
                "page_count": document.get("page_count") or 0,
                "message": "Identical file already stored for this patient; existing extraction reused.",
            },
        }

    storage_path = _store_bytes(patient_id, filename, content)
    repository.update_document(document["id"], storage_path=storage_path, processing_status="EXTRACTING")

    result = extract_pdf_text(content)
    if not result.ok:
        repository.update_document(
            document["id"],
            processing_status="EXTRACTION_FAILED",
            page_count=result.page_count or 0,
            extraction_quality=0.0,
        )
        repository.log_audit(patient_id, "ingestion", "DOCUMENT_EXTRACTION_FAILED", {"document_id": document["id"], "error": result.error})
        return {
            "document": repository.get_document(document["id"]) or document,
            "duplicate": False,
            "created": created,
            "extraction": {
                "status": "EXTRACTION_FAILED",
                "page_count": result.page_count or 0,
                "error": result.error,
                "engine": result.engine,
                "message": "No text could be extracted. The file was stored unchanged and marked as failed.",
            },
        }

    pages = [
        {"page_number": page.page_number, "text": page.text, "ocr_required": page.ocr_required}
        for page in result.pages
    ]
    repository.save_pages(document["id"], pages)

    classification = document_classifier.classify_text(pages)
    status = "OCR_REQUIRED" if result.extraction_quality == 0 else "EXTRACTED"
    repository.update_document(
        document["id"],
        document_type=classification.document_type,
        document_date=classification.document_date,
        date_precision=classification.date_precision,
        page_count=result.page_count,
        processing_status=status,
        extraction_quality=result.extraction_quality,
        ocr_required_pages=json.dumps(result.ocr_required_pages),
    )
    repository.touch_patient(patient_id)
    repository.log_audit(
        patient_id,
        "ingestion",
        "DOCUMENT_INGESTED",
        {"document_id": document["id"], "pages": result.page_count, "engine": result.engine, "duplicate": not created},
    )

    return {
        "document": repository.get_document(document["id"]) or document,
        "duplicate": not created,
        "created": created,
        "extraction": {
            "status": status,
            "page_count": result.page_count,
            "engine": result.engine,
            "extraction_quality": result.extraction_quality,
            "ocr_required_pages": result.ocr_required_pages,
            "document_type": classification.document_type,
            "document_date": classification.document_date,
            "sections": classification.sections,
            "missing_information": classification.missing_information,
        },
    }

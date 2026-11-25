"""Document ingestion pipeline: validate, store, extract pages, classify, and OCR."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
from typing import Any

from backend import repository
from backend.config import settings
from backend.ingestion import document_classifier
from backend.ingestion.pdf_reader import ExtractedPage, extract_pdf_text, looks_like_pdf

try:
    import pymupdf  # type: ignore
except Exception:  # noqa: BLE001
    try:
        import fitz as pymupdf  # type: ignore
    except Exception:  # noqa: BLE001
        pymupdf = None


class IngestionError(ValueError):
    """Raised for a document that cannot be accepted."""


def get_tesseract_cmd() -> str | None:
    """Resolve the Tesseract OCR executable path if available."""
    configured = getattr(settings, "tesseract_cmd", "") or os.environ.get("TESSERACT_CMD", "")
    if configured and Path(configured).is_file():
        return str(Path(configured).resolve())

    which_path = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if which_path:
        return str(Path(which_path).resolve())

    standard_paths = [
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
    ]
    for p in standard_paths:
        if p.is_file():
            return str(p.resolve())

    return None


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
) -> dict[str, Any]:
    """Accept one PDF, persist metadata, extract text, run OCR if needed, and classify."""
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

    # Native PDF extraction
    result = extract_pdf_text(content)
    if not result.ok:
        repository.update_document(
            document["id"],
            processing_status="EXTRACTION_FAILED",
            page_count=result.page_count or 0,
            extraction_quality=0.0,
            ocr_required_pages=json.dumps([]),
        )
        repository.log_audit(
            patient_id,
            "ingestion",
            "DOCUMENT_EXTRACTION_FAILED",
            {"document_id": document["id"], "error": result.error},
        )
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

    # Attempt OCR on pages requiring it
    ocr_status_message: str | None = None
    if result.ocr_required_pages:
        tess_cmd = get_tesseract_cmd()
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            pytesseract = None
            Image = None
            ocr_status_message = f"Python OCR packages missing ({exc})."

        if ocr_status_message is None and not tess_cmd:
            ocr_status_message = (
                "Tesseract OCR executable not found on host. "
                "Install Tesseract-OCR to enable OCR extraction on scanned pages."
            )

        if ocr_status_message is None and pymupdf is None:
            ocr_status_message = "PyMuPDF not available for rasterizing PDF pages."

        if ocr_status_message is None:
            # All OCR requirements met! Execute OCR.
            assert pytesseract is not None
            assert Image is not None
            assert tess_cmd is not None
            pytesseract.pytesseract.tesseract_cmd = tess_cmd

            ocr_texts: dict[int, str] = {}
            ocr_error: str | None = None
            try:
                with pymupdf.open(stream=content, filetype="pdf") as doc:
                    for page_number in result.ocr_required_pages:
                        page = doc.load_page(page_number - 1)
                        pix = page.get_pixmap(dpi=300)
                        img = Image.open(io.BytesIO(pix.tobytes("png")))
                        text = pytesseract.image_to_string(img)
                        ocr_texts[page_number] = text.strip()
            except Exception as exc_ocr:
                ocr_error = str(exc_ocr)
                repository.log_audit(
                    patient_id,
                    "ingestion",
                    "OCR_EXECUTION_ERROR",
                    {"document_id": document["id"], "error": ocr_error},
                )

            if ocr_error is None:
                # Merge OCR text into pages
                for page in result.pages:
                    if page.page_number in ocr_texts:
                        ocr_result = ocr_texts[page.page_number]
                        if ocr_result:
                            page.text = (page.text + "\n" + ocr_result).strip() if page.text else ocr_result
                        if len(page.text.strip()) >= 40:
                            page.ocr_required = False

                # Recompute OCR required pages and extraction quality
                result.ocr_required_pages = [p.page_number for p in result.pages if p.ocr_required]
                if result.pages:
                    readable = sum(1 for p in result.pages if len(p.text.strip()) >= 40)
                    result.extraction_quality = round(readable / len(result.pages), 3)

                repository.log_audit(
                    patient_id,
                    "ingestion",
                    "OCR_EXECUTED",
                    {
                        "document_id": document["id"],
                        "pages_processed": len(ocr_texts),
                        "remaining_ocr_pages": result.ocr_required_pages,
                    },
                )
            else:
                ocr_status_message = f"OCR execution failed: {ocr_error}"
        else:
            # OCR unavailable
            repository.log_audit(
                patient_id,
                "ingestion",
                "OCR_UNAVAILABLE",
                {
                    "document_id": document["id"],
                    "reason": ocr_status_message,
                    "ocr_required_pages": result.ocr_required_pages,
                },
            )

    pages = [
        {"page_number": page.page_number, "text": page.text, "ocr_required": page.ocr_required}
        for page in result.pages
    ]
    repository.save_pages(document["id"], pages)

    classification = document_classifier.classify_text(pages)
    status = "OCR_REQUIRED" if result.ocr_required_pages else "EXTRACTED"
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
        {
            "document_id": document["id"],
            "pages": result.page_count,
            "engine": result.engine,
            "duplicate": not created,
            "processing_status": status,
        },
    )

    extraction_response: dict[str, Any] = {
        "status": status,
        "page_count": result.page_count,
        "engine": result.engine,
        "extraction_quality": result.extraction_quality,
        "ocr_required_pages": result.ocr_required_pages,
        "document_type": classification.document_type,
        "document_date": classification.document_date,
        "sections": classification.sections,
        "missing_information": classification.missing_information,
    }
    if ocr_status_message:
        extraction_response["ocr_message"] = ocr_status_message

    return {
        "document": repository.get_document(document["id"]) or document,
        "duplicate": not created,
        "created": created,
        "extraction": extraction_response,
    }

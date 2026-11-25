"""Tests for PDF text extraction, OCR detection/execution, and SQLite persistence."""

from __future__ import annotations

import io
import json
import uuid
import pytest
from PIL import Image, ImageDraw

from backend import repository
from backend.ingestion.pipeline import (
    IngestionError,
    get_tesseract_cmd,
    ingest_document,
)


def make_text_pdf(lines: list[str]) -> bytes:
    """Create a text-based PDF using PyMuPDF."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    blob = doc.tobytes()
    doc.close()
    return blob


def make_image_only_pdf(text_in_image: str = "Scanned Medical Report Page 1") -> bytes:
    """Create a PDF containing only a raster image and no selectable text."""
    fitz = pytest.importorskip("fitz")

    # Render an image using PIL
    img = Image.new("RGB", (600, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), text_in_image, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    page.insert_image(fitz.Rect(0, 0, 600, 400), stream=png_bytes)
    blob = doc.tobytes()
    doc.close()
    return blob


def test_normal_text_pdf_native_extraction():
    """1. Normal text PDF uses native extraction and persists text to SQLite."""
    patient_id = "test-patient-native-01"
    content = make_text_pdf([
        "Clinical Summary - Outpatient Note",
        "Patient exhibits persistent hypertension.",
        "Prescribed Lisinopril 10mg daily by Dr. Sarah Smith.",
        "Patient advised on low-sodium dietary modifications.",
    ])

    result = ingest_document(patient_id, "clinical_summary.pdf", content)

    doc = result["document"]
    extraction = result["extraction"]

    assert extraction["status"] == "EXTRACTED"
    assert extraction["page_count"] == 1
    assert extraction["ocr_required_pages"] == []
    assert extraction["extraction_quality"] >= 0.5
    assert not result["duplicate"]
    assert result["created"]

    # Verify SQLite persistence
    stored_doc = repository.get_document(doc["id"])
    assert stored_doc is not None
    assert stored_doc["processing_status"] == "EXTRACTED"
    assert stored_doc["page_count"] == 1

    stored_pages = repository.list_pages(doc["id"])
    assert len(stored_pages) == 1
    page1 = stored_pages[0]
    assert page1["page_number"] == 1
    assert "Lisinopril" in page1["text"]
    assert page1["ocr_required"] == 0
    assert page1["char_count"] > 40


def test_image_only_pdf_detected_as_requiring_ocr():
    """2. An image-only PDF is detected as requiring OCR and flags pages appropriately."""
    patient_id = "test-patient-ocr-detect-01"
    content = make_image_only_pdf("Clinical Ultrasound Scan")

    result = ingest_document(patient_id, "scan.pdf", content)

    doc = result["document"]
    extraction = result["extraction"]

    # Page 1 must be flagged as requiring OCR
    assert 1 in extraction["ocr_required_pages"]
    assert extraction["page_count"] == 1

    # Verify SQLite persistence of document and pages
    stored_doc = repository.get_document(doc["id"])
    assert stored_doc is not None
    assert stored_doc["page_count"] == 1

    # In our repository, ocr_required_pages is decoded to a list
    assert 1 in stored_doc["ocr_required_pages"]

    stored_pages = repository.list_pages(doc["id"])
    assert len(stored_pages) == 1
    page1 = stored_pages[0]
    assert page1["page_number"] == 1
    assert page1["ocr_required"] == 1

    # Check whether Tesseract binary was available
    tess_cmd = get_tesseract_cmd()
    if tess_cmd is None:
        # Tesseract is not installed on host -> OCR could not run
        assert extraction["status"] == "OCR_REQUIRED"
        assert "ocr_message" in extraction
        assert "Tesseract" in extraction["ocr_message"]
        assert stored_doc["processing_status"] == "OCR_REQUIRED"


def test_ocr_simulated_execution_and_persistence(monkeypatch):
    """3 & 4. Verify OCR execution branch: replaces empty text and persists to SQLite."""
    import pytesseract

    # Mock pytesseract.image_to_string to simulate successful OCR output
    mock_ocr_text = (
        "CONFIDENTIAL MEDICAL REPORT\n"
        "Patient ID: 99482\n"
        "Condition: Acute Bronchitis\n"
        "Treatment: Albuterol inhaler prescribed"
    )
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *args, **kwargs: mock_ocr_text)

    # Force get_tesseract_cmd to return a non-None path so the OCR execution branch triggers
    monkeypatch.setattr("backend.ingestion.pipeline.get_tesseract_cmd", lambda: "mock_tesseract.exe")

    patient_id = "test-patient-ocr-exec-01"
    content = make_image_only_pdf("Scanned Page")

    result = ingest_document(patient_id, "scanned_doc.pdf", content)

    doc = result["document"]
    extraction = result["extraction"]

    # Since OCR succeeded and provided >40 characters, OCR is no longer required
    assert extraction["status"] == "EXTRACTED"
    assert extraction["ocr_required_pages"] == []
    assert extraction["extraction_quality"] == 1.0

    # Verify SQLite persistence of OCR text
    stored_doc = repository.get_document(doc["id"])
    assert stored_doc["processing_status"] == "EXTRACTED"
    assert stored_doc["ocr_required_pages"] == []

    stored_pages = repository.list_pages(doc["id"])
    assert len(stored_pages) == 1
    page1 = stored_pages[0]
    assert page1["page_number"] == 1
    assert "Acute Bronchitis" in page1["text"]
    assert "Albuterol" in page1["text"]
    assert page1["ocr_required"] == 0
    assert page1["char_count"] == len(mock_ocr_text)


def test_real_tesseract_execution():
    """Verify real Tesseract execution on host if installed."""
    tess_cmd = get_tesseract_cmd()
    if tess_cmd is None:
        pytest.skip("Tesseract executable not installed on Windows host (BLOCKED/NOT_TESTED).")

    patient_id = "test-patient-real-tess"
    content = make_image_only_pdf("GENUINE OCR TEXT FROM SCANNED RECORD")
    result = ingest_document(patient_id, "real_scan.pdf", content)
    assert result["extraction"]["status"] == "EXTRACTED"


def test_multiple_pdfs_same_patient_no_overwrite():
    """5. Multiple PDFs uploaded for the same patient are all preserved without overwriting."""
    patient_id = f"test-patient-multi-doc-{uuid.uuid4().hex[:8]}"

    doc1_content = make_text_pdf([
        "Document 1: Initial Consultation",
        "Patient diagnosed with mild asthma.",
        "Follow up scheduled in six months.",
    ])
    doc2_content = make_text_pdf([
        "Document 2: Laboratory Report",
        "Complete Blood Count within normal limits.",
        "Hemoglobin 14.2 g/dL, Platelets 250k.",
    ])

    res1 = ingest_document(patient_id, "consultation.pdf", doc1_content)
    res2 = ingest_document(patient_id, "lab_report.pdf", doc2_content)

    doc1_id = res1["document"]["id"]
    doc2_id = res2["document"]["id"]

    # Ensure two distinct document records
    assert doc1_id != doc2_id

    # Retrieve all documents for the patient
    patient_docs = repository.list_documents(patient_id)
    assert len(patient_docs) == 2

    stored_ids = {d["id"] for d in patient_docs}
    assert doc1_id in stored_ids
    assert doc2_id in stored_ids

    # Verify pages for both documents are preserved independently
    pages1 = repository.list_pages(doc1_id)
    pages2 = repository.list_pages(doc2_id)

    assert len(pages1) == 1
    assert "mild asthma" in pages1[0]["text"]

    assert len(pages2) == 1
    assert "Hemoglobin 14.2" in pages2[0]["text"]


def test_duplicate_pdf_reuses_existing_record():
    """Duplicate PDF uploads for the same patient reuse the existing record."""
    patient_id = "test-patient-duplicate-01"
    content = make_text_pdf([
        "Document: Duplicate Test",
        "This content is uploaded twice to verify deduplication.",
    ])

    res1 = ingest_document(patient_id, "original.pdf", content)
    assert res1["created"] is True
    assert res1["duplicate"] is False

    res2 = ingest_document(patient_id, "original_copy.pdf", content)
    assert res2["created"] is False
    assert res2["duplicate"] is True
    assert res2["document"]["id"] == res1["document"]["id"]


def test_invalid_pdf_raises_ingestion_error():
    """Invalid or empty file raises IngestionError and creates no document."""
    with pytest.raises(IngestionError, match="Uploaded file is empty"):
        ingest_document("test-err-patient", "empty.pdf", b"")

    with pytest.raises(IngestionError, match="missing %PDF header"):
        ingest_document("test-err-patient", "not_a_pdf.txt", b"Hello, world!")

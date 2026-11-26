"""Regression tests for the clinical structuring confidence-argument fix.

These reproduce the original TypeError ('got multiple values for keyword
argument confidence') across every extraction category and assert that
confidence metadata survives extraction.
"""

from __future__ import annotations

import pytest

from backend.clinical import entity_extractor
from backend.ingestion.document_classifier import normalize_date


def _doc():
    return {"id": "doc1", "filename": "discharge.pdf", "document_date": "2024-03-01", "data_origin": "USER_UPLOAD"}


def _page(text):
    return {"page_number": 1, "text": text}


def test_allergy_extraction_no_duplicate_confidence():
    pages = [_page("Allergy: Penicillin\nAllergies: NKDA")]
    entities = entity_extractor.extract_entities_from_pages(pages, _doc(), "p1")
    allergies = [e for e in entities if e["category"] == "ALLERGY"]
    assert allergies, "allergy extraction must produce entities"
    for e in allergies:
        assert "confidence" in e and e["confidence"] is not None


def test_medication_extraction_confidence():
    pages = [_page("Medications:\n- Metformin 500 mg twice daily")]
    entities = entity_extractor.extract_entities_from_pages(pages, _doc(), "p1")
    meds = [e for e in entities if e["category"] == "MEDICATION"]
    assert meds
    for e in meds:
        assert e["confidence"] is not None
        assert (e.get("attributes") or {}).get("dose") == "500 mg"


def test_diagnosis_extraction_confidence():
    pages = [_page("Diagnosis: Type 2 diabetes mellitus")]
    entities = entity_extractor.extract_entities_from_pages(pages, _doc(), "p1")
    dx = [e for e in entities if e["category"] == "DIAGNOSIS"]
    assert dx
    for e in dx:
        assert e["confidence"] is not None


def test_lab_extraction_confidence():
    pages = [_page("Laboratory:\nCreatinine 1.1 mg/dL")]
    entities = entity_extractor.extract_entities_from_pages(pages, _doc(), "p1")
    labs = [e for e in entities if e["category"] == "LAB_RESULT"]
    assert labs
    for e in labs:
        assert e["confidence"] is not None


def test_vital_extraction_confidence():
    pages = [_page("Vitals: Blood pressure 120/80 mmHg")]
    entities = entity_extractor.extract_entities_from_pages(pages, _doc(), "p1")
    vitals = [e for e in entities if e["category"] == "VITAL_SIGN"]
    assert vitals
    for e in vitals:
        assert e["confidence"] is not None


def test_procedure_and_symptom_lines_do_not_crash():
    """Procedure/symptom lines must not raise the duplicate-confidence TypeError.

    The extractor does not currently emit PROCEDURE/SYMPTOM entities for these
    inputs, so we only assert no exception and that any emitted entity carries
    confidence metadata.
    """
    pages = [_page("Procedure: Echocardiogram\nSymptoms: chest pain, dyspnea")]
    entities = entity_extractor.extract_entities_from_pages(pages, _doc(), "p1")
    for e in entities:
        assert e.get("confidence") is not None


def test_all_categories_combined_no_exception():
    """Reproduces the original discharge.pdf scenario that triggered the TypeError."""
    text = (
        "Discharge Summary\n"
        "Patient: Test Patient\n"
        "Date: 2024-03-01\n"
        "Diagnosis: Type 2 diabetes mellitus\n"
        "Medications:\n"
        "- Metformin 500 mg twice daily\n"
        "Allergy: Penicillin\n"
        "Laboratory:\n"
        "HbA1c 7.2 %\n"
        "Vitals: Blood pressure 120/80 mmHg\n"
        "Procedure: Echocardiogram\n"
        "Symptoms: chest pain\n"
    )
    pages = [_page(text)]
    # Must not raise TypeError: got multiple values for keyword argument 'confidence'
    entities = entity_extractor.extract_entities_from_pages(pages, _doc(), "p1")
    assert entities
    categories = {e["category"] for e in entities}
    assert "DIAGNOSIS" in categories
    assert "MEDICATION" in categories
    assert "ALLERGY" in categories
    for e in entities:
        assert e.get("confidence") is not None, e

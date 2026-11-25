"""Deterministic document classification, date detection and section mapping.

This runs before any model call: it gives the Document Intelligence Agent a
verifiable baseline and keeps the pipeline usable without an API key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DOCUMENT_TYPES = [
    "DISCHARGE_SUMMARY",
    "PRESCRIPTION",
    "LAB_REPORT",
    "DIAGNOSTIC_REPORT",
    "CONSULTATION_NOTE",
    "MEDICAL_HISTORY",
    "UNKNOWN",
]

_TYPE_KEYWORDS: dict[str, list[str]] = {
    "DISCHARGE_SUMMARY": ["discharge summary", "discharge", "admitted", "admission date", "hospital course"],
    "PRESCRIPTION": ["prescription", "rx:", "rx ", "sig:", "dispense", "refill", "tablet", "capsule"],
    "LAB_REPORT": [
        "laboratory report",
        "lab report",
        "haematology",
        "hematology",
        "biochemistry",
        "specimen",
        "reference range",
        "collection date",
    ],
    "DIAGNOSTIC_REPORT": ["radiology", "impression:", "ct scan", "mri", "x-ray", "ultrasound", "ecg", "echocardiogram"],
    "CONSULTATION_NOTE": ["consultation", "consult note", "clinic note", "progress note", "seen in clinic", "review"],
    "MEDICAL_HISTORY": ["medical history", "past history", "history of present illness", "immunization", "family history"],
}

_SECTION_KEYWORDS: dict[str, list[str]] = {
    "medications": ["medication", "medications", "rx", "drug", "tablet", "capsule", "dose", "mg"],
    "diagnoses": ["diagnosis", "diagnoses", "impression", "assessment", "condition", "problem list"],
    "allergies": ["allergy", "allergies", "adverse reaction", "nkda", "intolerance"],
    "laboratory": ["laboratory", "lab", "hba1c", "creatinine", "haemoglobin", "hemoglobin", "cholesterol", "glucose", "sodium"],
    "procedures": ["procedure", "surgery", "operation", "performed", "intervention"],
    "vitals": ["blood pressure", "heart rate", "temperature", "weight", "bmi", "pulse"],
    "plan": ["plan", "follow-up", "follow up", "advice", "recommend"],
}

_LABELLED_DATE_PATTERNS = [
    ("discharge", r"discharge\s+date\s*[:\-]\s*([0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4})"),
    ("admission", r"admission\s+date\s*[:\-]\s*([0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4})"),
    ("collection", r"collection\s+date\s*[:\-]\s*([0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4})"),
    ("service", r"(?:date\s+of\s+service|service\s+date)\s*[:\-]\s*([0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4})"),
    ("visit", r"visit\s+date\s*[:\-]\s*([0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4})"),
    ("report", r"report\s+date\s*[:\-]\s*([0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4})"),
    ("prescription", r"prescription\s+date\s*[:\-]\s*([0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4})"),
    ("generic", r"(?<!admission )(?<!discharge )date\s*[:\-]\s*([0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4})"),
]

_TEXTUAL_DATE = r"([0-9]{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+[0-9]{4})"

_PREFERRED_LABEL = {
    "DISCHARGE_SUMMARY": ["discharge", "admission", "generic"],
    "LAB_REPORT": ["collection", "report", "generic"],
    "PRESCRIPTION": ["prescription", "generic"],
    "CONSULTATION_NOTE": ["visit", "service", "generic"],
    "DIAGNOSTIC_REPORT": ["service", "report", "generic"],
    "MEDICAL_HISTORY": ["generic"],
    "UNKNOWN": ["generic"],
}


@dataclass
class DocumentClassification:
    document_type: str = "UNKNOWN"
    document_date: str | None = None
    date_precision: str = "UNKNOWN"
    sections: list[str] = field(default_factory=list)
    relevant_pages: list[int] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)


def normalize_date(raw: str) -> tuple[str | None, str]:
    """Normalize a date to ISO-8601 where the format is unambiguous."""
    text = raw.strip().lower()
    match = re.fullmatch(r"([0-9]{4})[./\-]([0-9]{1,2})[./\-]([0-9]{1,2})", text)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}", "DAY"
    match = re.fullmatch(r"([0-9]{1,2})[./\-]([0-9]{1,2})[./\-]([0-9]{4})", text)
    if match:
        first, second, year = match.groups()
        day, month = (int(first), int(second)) if int(first) > 12 else (int(second), int(first))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{int(year):04d}-{month:02d}-{day:02d}", "DAY"
        return None, "UNKNOWN"
    match = re.fullmatch(_TEXTUAL_DATE, text)
    if match:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        day, month_name, year = re.match(r"([0-9]{1,2})\s+([a-z]+)\s+([0-9]{4})", text).groups()  # type: ignore[union-attr]
        month = months.get(month_name[:3])
        if month:
            return f"{int(year):04d}-{month:02d}-{int(day):02d}", "DAY"
    return None, "UNKNOWN"


def detect_document_date(text: str, document_type: str) -> tuple[str | None, str]:
    """Find the clinical document date using labelled patterns only."""
    found: dict[str, tuple[str, str]] = {}
    for label, pattern in _LABELLED_DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            iso, precision = normalize_date(match.group(1))
            if iso:
                found[label] = (iso, precision)
    for label in _PREFERRED_LABEL.get(document_type, ["generic"]):
        if label in found:
            return found[label]
    if found:
        return next(iter(found.values()))
    return None, "UNKNOWN"


def classify_text(pages: list[dict]) -> DocumentClassification:
    """Classify a document from its extracted pages."""
    full_text = "\n".join(page.get("text", "") for page in pages)
    lowered = full_text.lower()
    result = DocumentClassification()

    scores = {doc_type: 0 for doc_type in DOCUMENT_TYPES}
    for doc_type, keywords in _TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                scores[doc_type] += 1
    best_type = max(scores, key=lambda key: scores[key])
    result.document_type = best_type if scores[best_type] > 0 else "UNKNOWN"

    result.document_date, result.date_precision = detect_document_date(full_text, result.document_type)

    for section, keywords in _SECTION_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            result.sections.append(section)

    for page in pages:
        page_text = (page.get("text") or "").lower()
        if any(any(keyword in page_text for keyword in keywords) for keywords in _SECTION_KEYWORDS.values()):
            result.relevant_pages.append(int(page.get("page_number", 0)))
    if not result.relevant_pages and pages:
        result.relevant_pages = [int(pages[0].get("page_number", 1))]

    patient_match = re.search(r"patient\s*(?:id|identifier)\s*[:\-]\s*([A-Za-z0-9\-_/]+)", full_text, re.IGNORECASE)
    if patient_match:
        result.observations.append(f"Patient identifier present in document: {patient_match.group(1)}")
    if result.document_date:
        result.observations.append(f"Clinical document date detected: {result.document_date}")

    if result.document_type == "UNKNOWN":
        result.missing_information.append("Document type could not be determined from its text")
    if not result.document_date:
        result.missing_information.append("No labelled clinical date found in the document text")
    if "medications" not in result.sections:
        result.missing_information.append("No medication section detected")
    if "diagnoses" not in result.sections:
        result.missing_information.append("No diagnosis section detected")

    return result

"""Deterministic clinical entity extraction with page-level provenance.

This module is the verifiable baseline for the Clinical Structuring Agent. It
never invents values: anything it cannot read stays absent, and every entity
keeps the original wording plus the page and snippet it came from.
"""

from __future__ import annotations

import re

from backend.db import new_id
from backend.ingestion.document_classifier import normalize_date

MEDICATION_FORMS = (
    "tablet", "tablets", "tab", "tabs", "capsule", "capsules", "cap", "syrup",
    "suspension", "injection", "inj", "inhaler", "cream", "ointment", "drops",
    "solution", "spray", "patch", "sachet", "gel",
)

_DOSE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|µg|g|ml|iu|units?|%)\b", re.IGNORECASE)
_FREQ = re.compile(
    r"\b(once daily|twice daily|three times daily|four times daily|once a day|twice a day|"
    r"every\s+\d+\s+hours|every\s+\d+\s+days|od|bd|tds|tds\.|qid|qhs|qam|prn|nocte|daily|weekly|as needed)\b",
    re.IGNORECASE,
)
_ROUTE = re.compile(
    r"\b(oral(?:ly)?|p\.?o\.?|i\.?v\.?|i\.?m\.?|s\.?c\.?|subcutaneous|topical(?:ly)?|inhaled|inhalation|rectal|nasal|sublingual)\b",
    re.IGNORECASE,
)
_DURATION = re.compile(r"\b(?:for\s+)?(\d+)\s*(day|days|week|weeks|month|months)\b", re.IGNORECASE)
_STATUS = re.compile(
    r"\b(active|current|ongoing|continued|discontinued|stopped|ceased|completed|held|paused|not\s+active)\b",
    re.IGNORECASE,
)
_NKDA = re.compile(r"^(nkda|no known (?:drug )?allerg\w*|nil|none|no allergies)\b", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:[-*•·]|\d+[.)]|[a-z][.)])\s*", re.IGNORECASE)

_LAB_LINE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 /()\-\.]{1,40}?)\s*(?::|=)?\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z%µ/]+)?\s*(?:\((?P<range>[^)]{1,40})\))?\s*$"
)
_VITAL_BP = re.compile(r"\b(?:blood pressure|bp)\s*[:\-]?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*(mmhg)?", re.IGNORECASE)
_VITAL_SIMPLE = re.compile(
    r"\b(heart rate|pulse|temperature|weight|height|bmi|spo2|respiratory rate)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*([a-zA-Z%/]+)?",
    re.IGNORECASE,
)

_SECTION_HEADERS = {
    "medications": ["medication", "medications", "current medication", "discharge medication", "drug", "rx", "prescription"],
    "diagnoses": ["diagnosis", "diagnoses", "impression", "assessment", "condition", "problem list", "clinical findings"],
    "allergies": ["allergy", "allergies", "adverse reaction", "drug allergy"],
    "laboratory": ["laboratory", "lab", "results", "investigations", "biochemistry", "haematology", "hematology"],
    "procedures": ["procedure", "procedures", "surgery", "operations", "intervention"],
    "vitals": ["vitals", "vital signs", "measurements"],
    "symptoms": ["symptoms", "complaints", "presenting complaint"],
    "plan": ["plan", "management", "advice", "follow-up", "follow up"],
}

_DOSE_UNITS = {"mg", "mcg", "µg", "g", "ml", "iu", "unit", "units", "%"}

_SYNONYMS = [
    (r"\bhtn\b", "hypertension"),
    (r"\b(?:dm2|t2dm|type\s*(?:2|ii)\s*diabetes(?:\s*mellitus)?)\b", "type 2 diabetes mellitus"),
    (r"\b(?:dm1|t1dm|type\s*(?:1|i)\s*diabetes(?:\s*mellitus)?)\b", "type 1 diabetes mellitus"),
    (r"\bckd\b", "chronic kidney disease"),
    (r"\bcopd\b", "chronic obstructive pulmonary disease"),
    (r"\bcad\b", "coronary artery disease"),
    (r"\bchf\b", "congestive heart failure"),
    (r"\baf\b", "atrial fibrillation"),
    (r"\buti\b", "urinary tract infection"),
]


def _clean(line: str) -> str:
    return _BULLET.sub("", line).strip()


def _section_of(line: str) -> str | None:
    """Return the section a header-like line introduces, if any."""
    stripped = line.strip().rstrip(":").strip().lower()
    if not stripped or len(stripped.split()) > 4:
        return None
    if not (line.strip().endswith(":") or ":" in line):
        return None
    for section, keywords in _SECTION_HEADERS.items():
        if any(stripped == keyword or stripped.startswith(keyword) for keyword in keywords):
            return section
    return None


def normalize_condition(text: str) -> str:
    """Normalize a condition name without changing its clinical meaning."""
    value = text.lower().strip(" .,;:-")
    value = re.sub(r"[()]", " ", value)
    for pattern, replacement in _SYNONYMS:
        value = re.sub(pattern, replacement, value)
    value = re.sub(r"\s+", " ", value).strip(" .,;:-")
    return value


def normalize_medication(text: str) -> str:
    """Strip dose, frequency, route and dosage form to leave the drug name."""
    value = text.lower()
    value = _DOSE.sub(" ", value)
    value = _FREQ.sub(" ", value)
    value = _ROUTE.sub(" ", value)
    value = _DURATION.sub(" ", value)
    for form in MEDICATION_FORMS:
        value = re.sub(rf"\b{form}\b", " ", value)
    value = re.sub(r"[^a-z0-9\s\-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -")
    return value


def _medication_status(line: str) -> str:
    match = _STATUS.search(line)
    if not match:
        return "UNKNOWN"
    token = match.group(1).lower()
    if token in {"discontinued", "stopped", "ceased", "not active", "completed"}:
        return "DISCONTINUED"
    if token in {"held", "paused"}:
        return "HELD"
    return "ACTIVE"


def _medication_attributes(line: str) -> dict:
    dose = _DOSE.search(line)
    freq = _FREQ.search(line)
    route = _ROUTE.search(line)
    duration = _DURATION.search(line)
    return {
        "dose": f"{dose.group(1)} {dose.group(2)}" if dose else None,
        "dose_value": float(dose.group(1)) if dose else None,
        "dose_unit": dose.group(2).lower() if dose else None,
        "frequency": freq.group(1).lower() if freq else None,
        "route": route.group(1).lower().replace(".", "") if route else None,
        "duration": f"{duration.group(1)} {duration.group(2)}".lower() if duration else None,
        "status": _medication_status(line),
    }


def _entity(
    *,
    patient_id: str,
    category: str,
    original: str,
    normalized: str | None,
    document: dict,
    page_number: int,
    snippet: str,
    confidence: float,
    clinical_date: str | None,
    date_precision: str,
    attributes: dict | None = None,
) -> dict:
    return {
        "id": new_id("ent"),
        "patient_id": patient_id,
        "category": category,
        "original_value": original.strip()[:300],
        "normalized_value": (normalized or None),
        "clinical_date": clinical_date,
        "date_precision": date_precision,
        "source_type": "DOCUMENT",
        "source_document_id": document.get("id"),
        "source_document_name": document.get("filename"),
        "source_record_id": document.get("id"),
        "source_page": page_number,
        "evidence_snippet": snippet.strip()[:400],
        "confidence": confidence,
        "verification_status": "UNVERIFIED",
        "data_origin": document.get("data_origin") or "USER_UPLOAD",
        "attributes": attributes or {},
    }


def _condition_entities(text: str, **kwargs) -> list[dict]:
    parts = [part.strip() for part in re.split(r"[;,]", text) if part.strip()]
    entities = []
    for part in parts:
        if len(part) < 3:
            continue
        if _DOSE.search(part) and not re.search(r"[A-Za-z]{4}", part):
            continue
        entities.append(
            _entity(
                category="DIAGNOSIS",
                original=part,
                normalized=normalize_condition(part),
                attributes={},
                **kwargs,
            )
        )
    return entities


def _allergy_entities(text: str, **kwargs) -> list[dict]:
    if _NKDA.match(text.strip()):
        return [
            _entity(
                category="ALLERGY",
                original=text.strip(),
                normalized="no known drug allergy",
                confidence=0.9,
                attributes={"status": "NONE_RECORDED"},
                **kwargs,
            )
        ]
    parts = [part.strip() for part in re.split(r"[;,]", text) if part.strip()]
    entities = []
    for part in parts:
        if len(part) < 2:
            continue
        reaction = None
        reaction_match = re.search(r"\(([^)]+)\)", part)
        if reaction_match:
            reaction = reaction_match.group(1).strip()
        allergen = re.sub(r"\([^)]*\)", "", part).strip(" .,;:-")
        if not allergen:
            continue
        entities.append(
            _entity(
                category="ALLERGY",
                original=part,
                normalized=allergen.lower(),
                confidence=0.85,
                attributes={"reaction": reaction, "status": "RECORDED"},
                **kwargs,
            )
        )
    return entities


def _lab_entities(line: str, **kwargs) -> list[dict]:
    match = _LAB_LINE.match(line)
    if not match:
        return []
    name = match.group("name").strip(" .:-")
    unit = (match.group("unit") or "").lower()
    if not name or len(name) < 2 or unit in _DOSE_UNITS:
        return []
    if not re.search(r"[A-Za-z]{2}", name):
        return []
    if any(form in name.lower() for form in MEDICATION_FORMS):
        return []
    attributes = {
        "value": float(match.group("value")),
        "unit": unit or None,
        "reference_range": (match.group("range") or None),
    }
    return [
        _entity(
            category="LAB_RESULT",
            original=line,
            normalized=re.sub(r"\s+", " ", name.lower()),
            confidence=0.8,
            attributes=attributes,
            **kwargs,
        )
    ]


def extract_entities_from_pages(pages: list[dict], document: dict, patient_id: str) -> list[dict]:
    """Extract clinical entities from extracted pages, keeping provenance."""
    entities: list[dict] = []
    doc_date = document.get("document_date")
    doc_precision = "DAY" if doc_date else "UNKNOWN"

    for page in pages:
        page_number = int(page.get("page_number") or 1)
        text = page.get("text") or ""
        if not text.strip():
            continue
        current_section: str | None = None

        for raw_line in text.splitlines():
            line = _clean(raw_line)
            if not line or len(line) < 2:
                continue

            header_section = _section_of(raw_line)
            if header_section:
                current_section = header_section
                inline = raw_line.split(":", 1)[1].strip() if ":" in raw_line else ""
                if not inline:
                    continue
                line = _clean(inline)

            kwargs = dict(
                patient_id=patient_id,
                document=document,
                page_number=page_number,
                snippet=raw_line.strip(),
                clinical_date=doc_date,
                date_precision=doc_precision,
            )

            lowered = line.lower()
            labelled = re.match(
                r"^(?:discharge\s+)?(medications?|rx|current\s+medications?)\s*[:\-]\s*(.+)$", line, re.IGNORECASE
            )
            diagnosis_labelled = re.match(
                r"^(?:primary\s+|secondary\s+|final\s+)?(diagnosis|diagnoses|impression|assessment|condition)\s*[:\-]\s*(.+)$",
                line,
                re.IGNORECASE,
            )
            allergy_labelled = re.match(r"^(?:drug\s+)?allerg(?:y|ies)\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
            procedure_labelled = re.match(
                r"^(?:procedure|surgery|operation|intervention)\s*[:\-]\s*(.+)$", line, re.IGNORECASE
            )
            symptom_labelled = re.match(r"^(?:symptoms?|complaints?)\s*[:\-]\s*(.+)$", line, re.IGNORECASE)

            if labelled:
                body = labelled.group(2)
                for part in re.split(r";", body):
                    part = part.strip()
                    if not part or len(part) < 3:
                        continue
                    normalized = normalize_medication(part)
                    if not normalized:
                        continue
                    entities.append(
                        _entity(
                            category="MEDICATION",
                            original=part,
                            normalized=normalized,
                            confidence=0.9,
                            attributes=_medication_attributes(part),
                            **{**kwargs, "snippet": part},
                        )
                    )
                continue

            if diagnosis_labelled:
                entities.extend(
                    _condition_entities(diagnosis_labelled.group(2), **{**kwargs, "confidence": 0.9})
                )
                continue

            if allergy_labelled:
                entities.extend(
                    _allergy_entities(allergy_labelled.group(1), **{**kwargs, "confidence": 0.9})
                )
                continue

            if procedure_labelled:
                body = procedure_labelled.group(1).strip()
                if body:
                    entities.append(
                        _entity(
                            category="PROCEDURE",
                            original=body,
                            normalized=body.lower(),
                            confidence=0.85,
                            **kwargs,
                        )
                    )
                continue

            if symptom_labelled:
                body = symptom_labelled.group(1).strip()
                for part in re.split(r"[;,]", body):
                    part = part.strip()
                    if len(part) < 3:
                        continue
                    entities.append(
                        _entity(
                            category="SYMPTOM",
                            original=part,
                            normalized=part.lower(),
                            confidence=0.8,
                            **kwargs,
                        )
                    )
                continue

            blood_pressure = _VITAL_BP.search(line)
            if blood_pressure:
                entities.append(
                    _entity(
                        category="VITAL_SIGN",
                        original=line,
                        normalized="blood pressure",
                        confidence=0.85,
                        attributes={
                            "systolic": int(blood_pressure.group(1)),
                            "diastolic": int(blood_pressure.group(2)),
                            "unit": "mmHg",
                        },
                        **kwargs,
                    )
                )
                continue

            if current_section == "allergies":
                entities.extend(_allergy_entities(line, **{**kwargs, "confidence": 0.75}))
                continue

            if current_section == "diagnoses":
                entities.extend(_condition_entities(line, **{**kwargs, "confidence": 0.75}))
                continue

            looks_like_medication = bool(_DOSE.search(line)) and any(
                form in lowered for form in MEDICATION_FORMS
            )
            if current_section == "medications" or looks_like_medication:
                normalized = normalize_medication(line)
                if normalized and re.search(r"[a-z]{3}", normalized):
                    entities.append(
                        _entity(
                            category="MEDICATION",
                            original=line,
                            normalized=normalized,
                            confidence=0.85 if looks_like_medication else 0.7,
                            attributes=_medication_attributes(line),
                            **kwargs,
                        )
                    )
                continue

            if current_section in {"laboratory", None}:
                lab_entities = _lab_entities(line, **kwargs)
                if lab_entities:
                    entities.extend(lab_entities)
                    continue

            simple_vital = _VITAL_SIMPLE.search(line)
            if simple_vital:
                entities.append(
                    _entity(
                        category="VITAL_SIGN",
                        original=line,
                        normalized=simple_vital.group(1).lower(),
                        confidence=0.8,
                        attributes={
                            "value": float(simple_vital.group(2)),
                            "unit": (simple_vital.group(3) or None),
                        },
                        **kwargs,
                    )
                )

    return _dedupe(entities)


def _dedupe(entities: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    unique: list[dict] = []
    for entity in entities:
        key = (
            entity["category"],
            entity.get("normalized_value"),
            entity.get("source_document_id"),
            entity.get("source_page"),
            (entity.get("attributes") or {}).get("dose"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(entity)
    return unique


def extraction_quality(pages: list[dict], entities: list[dict], ocr_pages: list[int]) -> str:
    """Grade extraction quality from observable evidence only."""
    readable = [page for page in pages if (page.get("text") or "").strip()]
    if not pages:
        return "FAILED"
    if not readable:
        return "OCR_REQUIRED"
    if ocr_pages:
        return "PARTIAL"
    if len(entities) >= 3:
        return "HIGH"
    if entities:
        return "MEDIUM"
    return "LOW"


def entity_summary(entities: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in entities:
        counts[entity["category"]] = counts.get(entity["category"], 0) + 1
    return counts


def extract_line_date(line: str) -> tuple[str | None, str]:
    """Extract an explicit date written on a clinical line."""
    match = re.search(r"([0-9]{4}[./\-][0-9]{1,2}[./\-][0-9]{1,2}|[0-9]{1,2}[./\-][0-9]{1,2}[./\-][0-9]{4})", line)
    if match:
        return normalize_date(match.group(1))
    return None, "UNKNOWN"

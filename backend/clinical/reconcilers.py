"""Cross-document comparison that proposes potential discrepancies.

Rules encoded here are deliberately conservative: a chronological change is not
a contradiction, missing information is not contradiction, and no function ever
decides which record is clinically correct.
"""

from __future__ import annotations

import re

from backend import repository
from backend.db import new_id

_TEMPORAL_MARKERS = re.compile(r"\b(history of|past history|previous|resolved|prior|old)\b", re.IGNORECASE)

_GLUCOSE_CONVERSIONS = {
    ("mmol/l", "mg/dl"): 18.0,
    ("mg/dl", "mmol/l"): 1 / 18.0,
}
_CREATININE_CONVERSIONS = {
    ("umol/l", "mg/dl"): 1 / 88.4,
    ("µmol/l", "mg/dl"): 1 / 88.4,
    ("mg/dl", "umol/l"): 88.4,
    ("mg/dl", "µmol/l"): 88.4,
}


def _source_reference(entity: dict) -> dict:
    return {
        "document_id": entity.get("source_document_id"),
        "document_name": entity.get("source_document_name"),
        "page": entity.get("source_page"),
        "snippet": entity.get("evidence_snippet"),
        "clinical_date": entity.get("clinical_date"),
        "entity_id": entity.get("id"),
    }


def _compared_value(entity: dict, value: str | None) -> str | None:
    # Kept as the plain value string: ConflictProposal.compared_values is a
    # list[str] and the verifier re-checks proposals against stored entities.
    return value


def _proposal(
    *,
    patient_id: str,
    category: str,
    subtype: str,
    description: str,
    entities: list[dict],
    values: list[str | None],
    reason: str,
    possible_explanation: str,
    severity: str,
    confidence: float,
) -> dict:
    origins = {entity.get("data_origin") for entity in entities}
    return {
        "id": new_id("cfl"),
        "patient_id": patient_id,
        "category": category,
        "subtype": subtype,
        "description": description,
        "compared_entity_ids": [entity.get("id") for entity in entities],
        "compared_values": [
            _compared_value(entity, value) for entity, value in zip(entities, values)
        ],
        "source_references": [_source_reference(entity) for entity in entities],
        "reason": reason,
        "possible_explanation": possible_explanation,
        "severity": severity,
        "confidence": confidence,
        "verification_status": "PENDING_VERIFICATION",
        "review_status": "NOT_REQUIRED",
        "data_origin": sorted(origin for origin in origins if origin)[0] if origins else "USER_UPLOAD",
    }


def _dates_ordered(first: str | None, second: str | None) -> bool:
    return bool(first and second and first != second)


def _condition_status(original: str | None) -> str:
    return "HISTORICAL" if original and _TEMPORAL_MARKERS.search(original) else "CURRENT"


def _group_by_document(entities: list[dict], key) -> dict:
    grouped: dict = {}
    for entity in entities:
        grouped.setdefault(key(entity), []).append(entity)
    return grouped


def compare_medications(entities: list[dict], patient_id: str) -> list[dict]:
    """Compare medication records that share the same normalized drug name."""
    proposals: list[dict] = []
    medications = [entity for entity in entities if entity.get("category") == "MEDICATION"]
    for name, group in _group_by_document(medications, lambda entity: entity.get("normalized_value")).items():
        if not name or len(group) < 2:
            continue
        documents = {entity.get("source_document_id") for entity in group}
        if len(documents) < 2:
            continue
        for index, first in enumerate(group):
            for second in group[index + 1:]:
                if first.get("source_document_id") == second.get("source_document_id"):
                    continue
                first_attrs = first.get("attributes") or {}
                second_attrs = second.get("attributes") or {}
                dose_first, dose_second = first_attrs.get("dose"), second_attrs.get("dose")
                freq_first, freq_second = first_attrs.get("frequency"), second_attrs.get("frequency")
                status_first, status_second = first_attrs.get("status"), second_attrs.get("status")

                if dose_first and dose_second and dose_first != dose_second:
                    same_date = (
                        first.get("clinical_date")
                        and first.get("clinical_date") == second.get("clinical_date")
                    )
                    if same_date:
                        proposals.append(
                            _proposal(
                                patient_id=patient_id,
                                category="MEDICATION",
                                subtype="DOSE_DIFFERENCE",
                                description=(
                                    f"{name} is recorded as {dose_first} in "
                                    f"{first.get('source_document_name')} and {dose_second} in "
                                    f"{second.get('source_document_name')} on the same clinical date "
                                    f"({first.get('clinical_date')})."
                                ),
                                entities=[first, second],
                                values=[dose_first, dose_second],
                                reason="Two documents dated the same day state different doses for the same medication.",
                                possible_explanation=(
                                    "Different dose strengths or a transcription difference between the two "
                                    "documents; the records cannot establish which statement applies."
                                ),
                                severity="HIGH",
                                confidence=0.72,
                            )
                        )
                    elif _dates_ordered(first.get("clinical_date"), second.get("clinical_date")):
                        proposals.append(
                            _proposal(
                                patient_id=patient_id,
                                category="MEDICATION",
                                subtype="DOSE_CHANGE_OVER_TIME",
                                description=(
                                    f"{name} dose differs between {first.get('clinical_date')} "
                                    f"({dose_first}) and {second.get('clinical_date')} ({dose_second})."
                                ),
                                entities=[first, second],
                                values=[dose_first, dose_second],
                                reason="Doses differ and the records carry different clinical dates.",
                                possible_explanation="Documented dose change over time; may be a legitimate titration.",
                                severity="LOW",
                                confidence=0.5,
                            )
                        )
                    else:
                        proposals.append(
                            _proposal(
                                patient_id=patient_id,
                                category="MEDICATION",
                                subtype="DOSE_DIFFERENCE_UNDATED",
                                description=(
                                    f"{name} is recorded as {dose_first} in "
                                    f"{first.get('source_document_name')} and {dose_second} in "
                                    f"{second.get('source_document_name')} with no comparable clinical date."
                                ),
                                entities=[first, second],
                                values=[dose_first, dose_second],
                                reason="Doses differ but the dates cannot be ordered.",
                                possible_explanation="Undated records; chronology cannot be established from the documents.",
                                severity="MEDIUM",
                                confidence=0.6,
                            )
                        )

                if freq_first and freq_second and freq_first != freq_second:
                    if first.get("clinical_date") and first.get("clinical_date") == second.get("clinical_date"):
                        proposals.append(
                            _proposal(
                                patient_id=patient_id,
                                category="MEDICATION",
                                subtype="FREQUENCY_DIFFERENCE",
                                description=(
                                    f"{name} frequency is {freq_first} in {first.get('source_document_name')} "
                                    f"and {freq_second} in {second.get('source_document_name')} on the same date."
                                ),
                                entities=[first, second],
                                values=[freq_first, freq_second],
                                reason="Same-day documents state different dosing frequencies.",
                                possible_explanation="Possibly different administration times or a documentation difference.",
                                severity="MEDIUM",
                                confidence=0.65,
                            )
                        )

                statuses = {status_first, status_second}
                if "ACTIVE" in statuses and "DISCONTINUED" in statuses:
                    active = first if status_first == "ACTIVE" else second
                    stopped = second if active is first else first
                    same_date = (
                        active.get("clinical_date")
                        and active.get("clinical_date") == stopped.get("clinical_date")
                    )
                    if same_date or not _dates_ordered(active.get("clinical_date"), stopped.get("clinical_date")):
                        proposals.append(
                            _proposal(
                                patient_id=patient_id,
                                category="MEDICATION",
                                subtype="STATUS_CONFLICT",
                                description=(
                                    f"{name} is documented as active in {active.get('source_document_name')} "
                                    f"and discontinued in {stopped.get('source_document_name')}."
                                ),
                                entities=[active, stopped],
                                values=["ACTIVE", "DISCONTINUED"],
                                reason="One document states the medication is active while another states it was discontinued.",
                                possible_explanation=(
                                    "The medication may have been stopped between the documents, or the status "
                                    "may be recorded differently in each record."
                                ),
                                severity="HIGH",
                                confidence=0.7,
                            )
                        )
    return proposals


def compare_diagnoses(entities: list[dict], patient_id: str) -> list[dict]:
    """Compare diagnosis status for the same normalized condition."""
    proposals: list[dict] = []
    diagnoses = [entity for entity in entities if entity.get("category") == "DIAGNOSIS"]
    for name, group in _group_by_document(diagnoses, lambda entity: entity.get("normalized_value")).items():
        if not name or len(group) < 2:
            continue
        for index, first in enumerate(group):
            for second in group[index + 1:]:
                if first.get("source_document_id") == second.get("source_document_id"):
                    continue
                first_status = _condition_status(first.get("original_value"))
                second_status = _condition_status(second.get("original_value"))
                if first_status == second_status:
                    continue
                same_date = (
                    first.get("clinical_date")
                    and first.get("clinical_date") == second.get("clinical_date")
                )
                if same_date:
                    proposals.append(
                        _proposal(
                            patient_id=patient_id,
                            category="DIAGNOSIS",
                            subtype="STATUS_CONFLICT",
                            description=(
                                f"{name} is recorded as current in {first.get('source_document_name')} and as "
                                f"historical in {second.get('source_document_name')} on {first.get('clinical_date')}."
                            ),
                            entities=[first, second],
                            values=[first_status, second_status],
                            reason="Same-day documents describe the same condition with different status wording.",
                            possible_explanation="One record may describe resolved history while the other lists an active problem.",
                            severity="MEDIUM",
                            confidence=0.6,
                        )
                    )
    return proposals


def compare_allergies(entities: list[dict], patient_id: str) -> list[dict]:
    """Compare allergy records across documents."""
    proposals: list[dict] = []
    allergies = [entity for entity in entities if entity.get("category") == "ALLERGY"]
    documents = {entity.get("source_document_id") for entity in allergies}
    if len(documents) < 2:
        return proposals

    recorded = [entity for entity in allergies if (entity.get("attributes") or {}).get("status") == "RECORDED"]
    none_recorded = [entity for entity in allergies if (entity.get("attributes") or {}).get("status") == "NONE_RECORDED"]

    for negative in none_recorded:
        for positive in recorded:
            if negative.get("source_document_id") == positive.get("source_document_id"):
                continue
            proposals.append(
                _proposal(
                    patient_id=patient_id,
                    category="ALLERGY",
                    subtype="ALLERGY_CONFLICT",
                    description=(
                        f"{positive.get('source_document_name')} records an allergy to "
                        f"{positive.get('normalized_value')} while {negative.get('source_document_name')} "
                        f"records no known allergies."
                    ),
                    entities=[positive, negative],
                    values=[positive.get("original_value"), negative.get("original_value")],
                    reason="One document documents an allergy and another documents no known allergies.",
                    possible_explanation=(
                        "Allergy documentation may be incomplete in one record; missing information does not "
                        "prove the allergy is absent."
                    ),
                    severity="HIGH",
                    confidence=0.7,
                )
            )

    for name, group in _group_by_document(
        recorded, lambda entity: entity.get("normalized_value")
    ).items():
        if not name or len(group) < 2:
            continue
        for index, first in enumerate(group):
            for second in group[index + 1:]:
                if first.get("source_document_id") == second.get("source_document_id"):
                    continue
                first_reaction = (first.get("attributes") or {}).get("reaction")
                second_reaction = (second.get("attributes") or {}).get("reaction")
                if first_reaction and second_reaction and first_reaction.lower() != second_reaction.lower():
                    proposals.append(
                        _proposal(
                            patient_id=patient_id,
                            category="ALLERGY",
                            subtype="REACTION_DIFFERENCE",
                            description=(
                                f"Allergy to {name} is documented with different reactions: "
                                f"'{first_reaction}' and '{second_reaction}'."
                            ),
                            entities=[first, second],
                            values=[first_reaction, second_reaction],
                            reason="The recorded reaction descriptions differ between documents.",
                            possible_explanation="Reaction may be described in different clinical language.",
                            severity="LOW",
                            confidence=0.55,
                        )
                    )
    return proposals


def _convert_lab(value: float, from_unit: str | None, to_unit: str | None) -> float | None:
    if not from_unit or not to_unit or from_unit == to_unit:
        return value
    factors = dict(_GLUCOSE_CONVERSIONS)
    factors.update(_CREATININE_CONVERSIONS)
    factor = factors.get((from_unit, to_unit))
    return value * factor if factor else None


def compare_laboratory_results(entities: list[dict], patient_id: str) -> list[dict]:
    """Compare same-lab values across documents after safe unit conversion."""
    proposals: list[dict] = []
    labs = [entity for entity in entities if entity.get("category") == "LAB_RESULT"]
    for name, group in _group_by_document(labs, lambda entity: entity.get("normalized_value")).items():
        if not name or len(group) < 2:
            continue
        for index, first in enumerate(group):
            for second in group[index + 1:]:
                if first.get("source_document_id") == second.get("source_document_id"):
                    continue
                first_attrs = first.get("attributes") or {}
                second_attrs = second.get("attributes") or {}
                first_value, second_value = first_attrs.get("value"), second_attrs.get("value")
                if first_value is None or second_value is None:
                    continue
                converted = _convert_lab(float(second_value), second_attrs.get("unit"), first_attrs.get("unit"))
                if converted is None:
                    continue
                if abs(float(first_value) - converted) < 1e-6:
                    continue
                same_date = (
                    first.get("clinical_date")
                    and first.get("clinical_date") == second.get("clinical_date")
                )
                if not same_date:
                    continue
                proposals.append(
                    _proposal(
                        patient_id=patient_id,
                        category="LABORATORY",
                        subtype="VALUE_DIFFERENCE",
                        description=(
                            f"{name} is {first_value} {first_attrs.get('unit') or ''} in "
                            f"{first.get('source_document_name')} and {second_value} "
                            f"{second_attrs.get('unit') or ''} in {second.get('source_document_name')} "
                            f"on the same clinical date."
                        ),
                        entities=[first, second],
                        values=[
                            f"{first_value} {first_attrs.get('unit') or ''}".strip(),
                            f"{second_value} {second_attrs.get('unit') or ''}".strip(),
                        ],
                        reason="Same-day laboratory results state different values for the same test.",
                        possible_explanation="Different specimens, repeat testing, or a transcription difference.",
                        severity="MEDIUM",
                        confidence=0.65,
                    )
                )
    return proposals


def compare_timeline(documents: list[dict], patient_id: str) -> list[dict]:
    """Detect internal chronological inconsistencies inside a document."""
    proposals: list[dict] = []
    for document in documents:
        text = (document.get("full_text") or repository.document_text(document["id"]) or "")
        admission = re.search(r"admission\s+date\s*[:\-]\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
        discharge = re.search(r"discharge\s+date\s*[:\-]\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
        if admission and discharge and discharge.group(1) < admission.group(1):
            proposals.append(
                {
                    "id": new_id("cfl"),
                    "patient_id": patient_id,
                    "category": "TIMELINE",
                    "subtype": "CHRONOLOGY_INCONSISTENCY",
                    "description": (
                        f"{document.get('filename')} records a discharge date "
                        f"({discharge.group(1)}) before its admission date ({admission.group(1)})."
                    ),
                    "compared_entity_ids": [],
                    "compared_values": [admission.group(1), discharge.group(1)],
                    "source_references": [
                        {
                            "document_id": document.get("id"),
                            "document_name": document.get("filename"),
                            "page": 1,
                            "snippet": admission.group(0),
                        }
                    ],
                    "reason": "The document states a discharge date earlier than its admission date.",
                    "possible_explanation": "Possible date entry error in the source document.",
                    "severity": "MEDIUM",
                    "confidence": 0.6,
                    "verification_status": "PENDING_VERIFICATION",
                    "review_status": "NOT_REQUIRED",
                    "data_origin": document.get("data_origin") or "USER_UPLOAD",
                }
            )
    return proposals


def propose_all(entities: list[dict], documents: list[dict], patient_id: str) -> list[dict]:
    """Run every comparison that the available data supports."""
    proposals: list[dict] = []
    proposals.extend(compare_medications(entities, patient_id))
    proposals.extend(compare_diagnoses(entities, patient_id))
    proposals.extend(compare_allergies(entities, patient_id))
    proposals.extend(compare_laboratory_results(entities, patient_id))
    proposals.extend(compare_timeline(documents, patient_id))
    return proposals

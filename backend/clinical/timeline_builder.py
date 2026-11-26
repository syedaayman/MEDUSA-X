"""Chronological reconstruction of a patient's record.

Events are derived only from stored clinical entities, so every timeline entry
keeps its document, page and snippet. Unknown dates stay at the end and keep
their imprecision instead of being invented.
"""

from __future__ import annotations

from typing import Any

from backend import repository
from backend.db import new_id

CATEGORY_ORDER = {
    "DIAGNOSIS": 0,
    "SYMPTOM": 1,
    "MEDICATION": 2,
    "ALLERGY": 3,
    "PROCEDURE": 4,
    "LAB_RESULT": 5,
    "VITAL_SIGN": 6,
    "PLAN": 7,
}

_CATEGORY_LABEL = {
    "DIAGNOSIS": "Diagnosis",
    "SYMPTOM": "Symptom",
    "MEDICATION": "Medication",
    "ALLERGY": "Allergy",
    "PROCEDURE": "Procedure",
    "LAB_RESULT": "Laboratory result",
    "VITAL_SIGN": "Vital sign",
    "PLAN": "Plan",
}


def describe_entity(entity: dict[str, Any]) -> str:
    """Render a clinical entity as a factual one-line description."""
    attributes = entity.get("attributes") or {}
    value = entity.get("original_value") or entity.get("normalized_value") or "unspecified"
    category = entity.get("category")
    if category == "MEDICATION":
        details = [
            attributes.get("dosage"),
            attributes.get("frequency"),
            attributes.get("route"),
            attributes.get("duration"),
        ]
        suffix = " ".join(part for part in details if part)
        status = attributes.get("status")
        text = f"{value} {suffix}".strip()
        if status:
            text = f"{text} ({status.lower().replace('_', ' ')})"
        return text
    if category in ("LAB_RESULT", "VITAL_SIGN"):
        parts = [value, attributes.get("unit")]
        text = " ".join(part for part in parts if part)
        if attributes.get("reference_range"):
            text = f"{text} (reference {attributes['reference_range']})"
        return text
    if category == "ALLERGY" and attributes.get("reaction"):
        return f"{value} — reaction: {attributes['reaction']}"
    return value


def build_events(patient_id: str, entities: list[dict] | None = None) -> list[dict]:
    """Group entities into deduplicated, chronologically ordered events."""
    if entities is None:
        entities = repository.list_entities(patient_id)

    grouped: dict[tuple, list[dict]] = {}
    for entity in entities:
        key = (
            entity.get("category"),
            (entity.get("normalized_value") or entity.get("original_value") or "").lower(),
            entity.get("clinical_date"),
            entity.get("document_id"),
        )
        grouped.setdefault(key, []).append(entity)

    events: list[dict] = []
    for (category, _normalized, clinical_date, document_id), group in grouped.items():
        primary = group[0]
        related = [item["id"] for item in group]
        document = repository.get_document(document_id) if document_id else None
        snippets = [item.get("evidence_snippet") for item in group if item.get("evidence_snippet")]
        events.append(
            {
                "event_id": new_id("evt"),
                "patient_id": patient_id,
                "event_date": clinical_date,
                "date_precision": primary.get("date_precision") or "UNKNOWN",
                "category": category,
                "description": describe_entity(primary),
                "related_entity_ids": related,
                "source_document_id": document_id,
                "source_document_name": (document or {}).get("filename"),
                "source_page": primary.get("source_page"),
                "evidence_snippet": snippets[0] if snippets else None,
                "verification_status": "SUPPORTED" if snippets else "UNVERIFIED",
                "data_origin": primary.get("data_origin") or "USER_UPLOAD",
                "_sort_page": primary.get("source_page") or 0,
            }
        )

    events.sort(
        key=lambda event: (
            event["event_date"] is None,
            event["event_date"] or "",
            CATEGORY_ORDER.get(event["category"], 9),
            event.get("_sort_page") or 0,
        )
    )
    for event in events:
        event.pop("_sort_page", None)
    return events


def persist_timeline(patient_id: str, entities: list[dict] | None = None) -> list[dict]:
    """Rebuild and store the patient timeline, returning the stored events."""
    events = build_events(patient_id, entities)
    repository.save_timeline(patient_id, events)
    return repository.list_timeline(patient_id)


def describe_changes(events: list[dict]) -> list[dict]:
    """Detect medication/diagnosis sequences that represent a change over time."""
    changes: list[dict] = []
    medications: dict[str, list[dict]] = {}
    for event in events:
        if event["category"] == "MEDICATION" and event.get("event_date"):
            key = (event["description"].split()[0] if event["description"] else "").lower()
            medications.setdefault(key, []).append(event)
    for key, group in medications.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda item: item["event_date"])
        distinct = {item["description"] for item in ordered}
        if len(distinct) > 1:
            changes.append(
                {
                    "category": "MEDICATION",
                    "subject": key,
                    "sequence": [
                        {"date": item["event_date"], "description": item["description"]} for item in ordered
                    ],
                    "note": "Documented medication sequence; treat as a change over time unless the sources are same-day and contradictory.",
                }
            )
    return changes


def summarise_timeline(events: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        counts[event["category"]] = counts.get(event["category"], 0) + 1
    return counts

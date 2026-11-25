"""Independent evidence verification.

The Evidence Verification Agent must not trust the reconciliation agent. This
module re-reads the stored page text for every compared entity, recomputes the
values from the entities themselves and returns an explicit decision.
"""

from __future__ import annotations

import re
from typing import Any

from backend import repository

VERIFIED = "VERIFIED_POTENTIAL_CONFLICT"
NOT_A_CONFLICT = "NOT_A_CONFLICT"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
NEEDS_REVIEW = "NEEDS_HUMAN_REVIEW"

_WS = re.compile(r"\s+")
_TEMPORAL = re.compile(r"\b(previous|prior|historical|history of|discontinued|stopped|switched|changed|now on|since)\b", re.I)


def _norm(text: str | None) -> str:
    return _WS.sub(" ", (text or "")).strip().lower()


def _snippet_present(snippet: str | None, page_text: str) -> bool:
    needle = _norm(snippet)
    if not needle:
        return False
    return needle[:160] in _norm(page_text)


def _value_key(entity: dict) -> str:
    attrs = entity.get("attributes") or {}
    parts = [
        entity.get("normalized_value") or "",
        str(attrs.get("dosage") or ""),
        str(attrs.get("frequency") or ""),
        str(attrs.get("route") or ""),
    ]
    return "|".join(part for part in parts if part)


def verify_conflict(patient_id: str, conflict: dict) -> dict[str, Any]:
    """Re-read the original sources for one proposed discrepancy."""
    checks: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    entity_ids = conflict.get("compared_entity_ids") or []
    entities: list[dict] = []
    for entity_id in entity_ids:
        entity = repository.get_entity(entity_id)
        if entity and entity.get("patient_id") == patient_id:
            entities.append(entity)

    check(
        "entities_resolved",
        len(entities) == len(entity_ids) and bool(entities),
        f"{len(entities)} of {len(entity_ids)} compared entities resolved for this patient",
    )

    if len(entities) < 2:
        return _result(conflict, INSUFFICIENT, checks, evidence, "The compared entities could not be resolved from stored records.")

    documents = {entity.get("document_id") for entity in entities}
    check("distinct_documents", len(documents) > 1, f"comparison spans {len(documents)} document(s)")

    source_ok = True
    for entity in entities:
        document_id = entity.get("document_id")
        page_number = entity.get("source_page")
        document = repository.get_document(document_id) if document_id else None
        page = repository.get_page(document_id, page_number) if document_id and page_number else None
        page_text = (page or {}).get("text") or ""
        found = _snippet_present(entity.get("evidence_snippet"), page_text)
        source_ok = source_ok and bool(document) and bool(page) and found
        evidence.append(
            {
                "entity_id": entity.get("id"),
                "document_id": document_id,
                "document_name": (document or {}).get("filename"),
                "page": page_number,
                "snippet": entity.get("evidence_snippet"),
                "original_value": entity.get("original_value"),
                "clinical_date": entity.get("clinical_date"),
                "snippet_found_on_page": found,
                "page_text_available": bool(page_text.strip()),
            }
        )
        check(
            f"snippet_on_page:{entity.get('id')}",
            found,
            f"source snippet re-read from page {page_number} of {(document or {}).get('filename') or 'unknown document'}",
        )

    values = [_value_key(entity) for entity in entities]
    check("values_differ", len(set(values)) > 1, "the compared clinical values are not identical")
    dates = [entity.get("clinical_date") for entity in entities]
    check("dates_recorded", all(dates), f"clinical dates present: {dates}")

    claimed = conflict.get("compared_values") or []
    claimed_values = {_norm(item.get("value") if isinstance(item, dict) else str(item)) for item in claimed}
    recomputed = {_norm(value) for value in values}
    check(
        "proposal_matches_entities",
        not claimed or claimed_values <= recomputed or bool(recomputed & claimed_values),
        "proposed values are reproducible from the stored entities",
    )

    snippets = " ".join(_norm(entity.get("evidence_snippet")) for entity in entities)
    temporal = bool(_TEMPORAL.search(snippets))
    same_date = len({date for date in dates if date}) == 1

    if not source_ok:
        return _result(
            conflict,
            INSUFFICIENT,
            checks,
            evidence,
            "At least one source snippet could not be re-read from the stored page text, so the finding is not evidence-backed.",
        )

    if len(documents) == 1:
        return _result(conflict, NOT_A_CONFLICT, checks, evidence, "Both values come from the same document; this is not a cross-document discrepancy.")

    if len(set(values)) == 1:
        return _result(conflict, NOT_A_CONFLICT, checks, evidence, "Recomputed clinical values are identical; nothing to reconcile.")

    if temporal and not same_date:
        return _result(
            conflict,
            NOT_A_CONFLICT,
            checks,
            evidence,
            "The sources describe an explicit change over time (previous/discontinued/new regimen), which is a legitimate clinical change rather than a contradiction.",
        )

    if not same_date and all(dates):
        ordered = sorted(dates)
        if ordered[0] != ordered[-1]:
            return _result(
                conflict,
                NEEDS_REVIEW,
                checks,
                evidence,
                "The values differ across documents with different clinical dates. This may be a documented change; a clinician must confirm before it is treated as a discrepancy.",
            )

    if conflict.get("category") == "LABORATORY" and not same_date:
        return _result(conflict, NEEDS_REVIEW, checks, evidence, "Laboratory values differ on different dates and may reflect a real trend.")

    return _result(
        conflict,
        VERIFIED,
        checks,
        evidence,
        "Both values are present on their cited pages, belong to this patient, are dated the same day and cannot be explained by a documented change over time.",
    )


def _result(conflict: dict, decision: str, checks: list[dict], evidence: list[dict], reason: str) -> dict[str, Any]:
    return {
        "conflict_id": conflict.get("id") or conflict.get("conflict_id"),
        "decision": decision,
        "verification_status": decision,
        "verification_reason": reason,
        "checks": checks,
        "evidence": evidence,
        "requires_human_review": decision in (NEEDS_REVIEW, INSUFFICIENT),
        "verified": decision == VERIFIED,
    }


def verify_all(patient_id: str, conflicts: list[dict]) -> list[dict]:
    return [verify_conflict(patient_id, conflict) for conflict in conflicts]

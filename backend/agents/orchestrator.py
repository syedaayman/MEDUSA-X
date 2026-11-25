"""MEDUSA-X orchestrator: a manager agent coordinating five specialists.

The orchestrator keeps control. It inspects the patient context, decides which
specialists are needed for the documents actually present, passes structured
results between them, verifies every proposal against original evidence and only
then builds the timeline and summary. Each step is recorded as real activity so
the dashboard reflects what happened, including failures.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError

from backend import repository
from backend.agents import sdk_runtime
from backend.agents.tools import ToolContext, ToolError  # noqa: F401 - re-exported for callers
from backend.agents import tools as agent_tools
from backend.clinical import entity_extractor
from backend.config import settings
from backend.db import utc_now
from backend.schemas import ClinicalEntity

ORCHESTRATOR = "ORCHESTRATOR"
DOCUMENT_INTELLIGENCE = "DOCUMENT_INTELLIGENCE"
CLINICAL_STRUCTURING = "CLINICAL_STRUCTURING"
RECONCILIATION = "RECONCILIATION"
EVIDENCE_VERIFICATION = "EVIDENCE_VERIFICATION"
TIMELINE_SUMMARY = "TIMELINE_SUMMARY"

COMPARABLE_CATEGORIES = {"MEDICATION", "DIAGNOSIS", "ALLERGY", "LAB_RESULT"}
MAX_SPECIALIST_RETRIES = 1


def _activity(run_id: str, agent: str, message: str, status: str = "RUNNING", detail: dict | None = None) -> None:
    repository.add_activity(run_id, agent, "STATUS", message, status=status, detail=detail or {})


def _with_retry(agent: str, run_id: str, label: str, fn: Callable[[], Any]) -> tuple[Any, str | None]:
    """Run a specialist step once, retrying a bounded number of times on error."""
    last_error: str | None = None
    for attempt in range(MAX_SPECIALIST_RETRIES + 1):
        try:
            return fn(), None
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < MAX_SPECIALIST_RETRIES:
                _activity(run_id, agent, f"{label} failed ({last_error}); retrying once", "RUNNING")
    return None, last_error


def _validate_entities(patient_id: str) -> tuple[int, list[str]]:
    """Deterministic Pydantic validation of what the structuring agent stored."""
    invalid: list[str] = []
    valid = 0
    for entity in repository.list_entities(patient_id):
        try:
            ClinicalEntity(**entity)
            valid += 1
        except ValidationError as exc:
            invalid.append(f"{entity.get('id')}: {exc.errors()[0].get('msg') if exc.errors() else exc}")
    return valid, invalid


def run_analysis(
    patient_id: str,
    document_ids: list[str] | None = None,
    run_id: str | None = None,
    focus: str = "",
) -> dict:
    """Execute the full agentic workflow for one patient and persist the results."""
    patient = repository.ensure_patient(patient_id)
    origin = patient.get("data_origin", "USER_UPLOAD")
    warnings: list[str] = []
    failures: list[str] = []
    metrics: dict[str, Any] = {}

    documents = [
        doc
        for doc in repository.list_documents(patient_id)
        if not document_ids or doc["id"] in set(document_ids)
    ]
    if run_id:
        run = repository.get_run(run_id) or repository.create_run(patient_id, [d["id"] for d in documents], "deterministic")
    else:
        run = repository.create_run(patient_id, [d["id"] for d in documents], "deterministic")
    run_id = run["id"]

    repository.update_run(run_id, status="RUNNING", current_agent=ORCHESTRATOR, started_at=run.get("started_at") or utc_now())
    _activity(
        run_id,
        ORCHESTRATOR,
        f"Received {len(documents)} document(s) for {patient_id} ({origin}). Building the workflow plan.",
    )

    if not documents:
        repository.update_run(run_id, status="FAILED", current_agent=None, completed_at=utc_now(), error_message="No documents available for this patient")
        _activity(run_id, ORCHESTRATOR, "No documents to analyse; workflow stopped.", "FAILED")
        return {"run_id": run_id, "status": "FAILED", "error": "No documents available for this patient"}

    # ------------------------------------------------ 1. document intelligence
    repository.update_run(run_id, current_agent=DOCUMENT_INTELLIGENCE)
    _activity(run_id, DOCUMENT_INTELLIGENCE, f"Classifying {len(documents)} document(s) and locating clinical sections.", "RUNNING")
    intel_ctx = ToolContext(run_id=run_id, patient_id=patient_id, agent=DOCUMENT_INTELLIGENCE)
    analysed: list[dict] = []
    ocr_documents: list[str] = []
    for document in documents:
        result, error = _with_retry(
            DOCUMENT_INTELLIGENCE,
            run_id,
            f"classification of {document.get('filename')}",
            lambda doc=document: agent_tools.classify_document(intel_ctx, doc["id"]),
        )
        if error or not result:
            failures.append(f"Document Intelligence failed on {document.get('filename')}: {error}")
            _activity(run_id, DOCUMENT_INTELLIGENCE, f"{document.get('filename')} could not be classified: {error}", "FAILED")
            continue
        analysed.append(result)
        if result.get("processing_status") == "OCR_REQUIRED":
            ocr_documents.append(document.get("filename") or document["id"])
    metrics["documents_analysed"] = len(analysed)
    _activity(
        run_id,
        DOCUMENT_INTELLIGENCE,
        f"{len(analysed)} document(s) classified"
        + (f"; OCR required for {len(ocr_documents)}" if ocr_documents else "")
        + ".",
        "COMPLETED" if analysed else "FAILED",
        detail={"documents": [{"id": d["document_id"], "type": d["document_type"], "date": d["document_date"]} for d in analysed]},
    )

    # -------------------------------------------------- 2. clinical structuring
    repository.update_run(run_id, current_agent=CLINICAL_STRUCTURING)
    _activity(run_id, CLINICAL_STRUCTURING, "Extracting structured clinical entities with page-level provenance.", "RUNNING")
    struct_ctx = ToolContext(run_id=run_id, patient_id=patient_id, agent=CLINICAL_STRUCTURING)
    extracted = 0
    for document in documents:
        result, error = _with_retry(
            CLINICAL_STRUCTURING,
            run_id,
            f"entity extraction for {document.get('filename')}",
            lambda doc=document: agent_tools.extract_clinical_entities(struct_ctx, doc["id"]),
        )
        if error or not result:
            failures.append(f"Clinical Structuring failed on {document.get('filename')}: {error}")
            _activity(run_id, CLINICAL_STRUCTURING, f"Extraction failed for {document.get('filename')}: {error}", "FAILED")
            continue
        extracted += int(result.get("stored") or 0)
    valid_entities, invalid_entities = _validate_entities(patient_id)
    metrics["entities_extracted"] = extracted
    metrics["entities_valid"] = valid_entities
    metrics["entities_invalid"] = len(invalid_entities)
    if invalid_entities:
        warnings.append(f"{len(invalid_entities)} stored entit(ies) failed schema validation and were excluded from results.")
    _activity(
        run_id,
        CLINICAL_STRUCTURING,
        f"{extracted} entity(ies) extracted; {valid_entities} passed schema validation.",
        "COMPLETED" if extracted else ("NEEDS_REVIEW" if ocr_documents else "COMPLETED"),
        detail={"entity_counts": entity_extractor.entity_summary(repository.list_entities(patient_id))},
    )

    # ------------------------------------- 3. orchestrator decides reconciliation
    repository.update_run(run_id, current_agent=ORCHESTRATOR)
    entities = repository.list_entities(patient_id)
    present_categories = {entity.get("category") for entity in entities}
    comparable = present_categories & COMPARABLE_CATEGORIES
    documents_with_entities = {entity.get("source_document_id") for entity in entities if entity.get("source_document_id")}
    reconcile_needed = len(documents_with_entities) >= 2 and bool(comparable)

    conflicts: list[dict] = []
    if reconcile_needed:
        _activity(
            run_id,
            ORCHESTRATOR,
            f"{len(documents_with_entities)} documents share comparable data ({', '.join(sorted(comparable))}); delegating reconciliation.",
        )
        repository.update_run(run_id, current_agent=RECONCILIATION)
        rec_ctx = ToolContext(run_id=run_id, patient_id=patient_id, agent=RECONCILIATION)
        result, error = _with_retry(RECONCILIATION, run_id, "reconciliation", lambda: agent_tools.compare_records(rec_ctx))
        if error or not result:
            failures.append(f"Reconciliation failed: {error}")
            _activity(run_id, RECONCILIATION, f"Reconciliation failed: {error}", "FAILED")
        else:
            conflicts = result.get("conflicts") or []
            _activity(run_id, RECONCILIATION, f"{len(conflicts)} potential discrepancy(ies) proposed for verification.", "COMPLETED")
    else:
        reason = (
            "Only one document contributes structured data, so no cross-document comparison was attempted."
            if len(documents_with_entities) < 2
            else "No comparable medication, diagnosis, allergy or laboratory entities were found."
        )
        _activity(run_id, RECONCILIATION, f"Skipped: {reason}", "SKIPPED")
    metrics["conflicts_proposed"] = len(conflicts)

    # ------------------------------------------------- 4. evidence verification
    verification_counts: dict[str, int] = {}
    if conflicts:
        repository.update_run(run_id, current_agent=EVIDENCE_VERIFICATION)
        _activity(run_id, EVIDENCE_VERIFICATION, f"Independently checking {len(conflicts)} proposal(s) against the original pages.", "RUNNING")
        verify_ctx = ToolContext(run_id=run_id, patient_id=patient_id, agent=EVIDENCE_VERIFICATION)
        for conflict in conflicts:
            result, error = _with_retry(
                EVIDENCE_VERIFICATION,
                run_id,
                f"verification of {conflict['id']}",
                lambda c=conflict: agent_tools.verify_evidence(verify_ctx, c["id"]),
            )
            if error or not result:
                failures.append(f"Evidence Verification failed on {conflict['id']}: {error}")
                _activity(run_id, EVIDENCE_VERIFICATION, f"{conflict['id']} could not be verified: {error}", "FAILED")
                repository.update_conflict_verification(
                    conflict["id"],
                    "NEEDS_HUMAN_REVIEW",
                    "Verification could not be completed automatically.",
                    requires_human_review=True,
                )
                verification_counts["NEEDS_HUMAN_REVIEW"] = verification_counts.get("NEEDS_HUMAN_REVIEW", 0) + 1
                continue
            decision = result.get("decision", "NEEDS_HUMAN_REVIEW")
            verification_counts[decision] = verification_counts.get(decision, 0) + 1
            if decision in ("INSUFFICIENT_EVIDENCE", "NEEDS_HUMAN_REVIEW"):
                agent_tools.request_human_review(verify_ctx, conflict["id"], result.get("verification_reason", ""))
        _activity(
            run_id,
            EVIDENCE_VERIFICATION,
            "Verification finished: " + ", ".join(f"{k.lower()} {v}" for k, v in sorted(verification_counts.items())) + ".",
            "COMPLETED",
            detail=verification_counts,
        )
    else:
        _activity(run_id, EVIDENCE_VERIFICATION, "No proposals to verify.", "SKIPPED")
    metrics["verification"] = verification_counts

    # ------------------------------------------------- 5. timeline and summary
    repository.update_run(run_id, current_agent=TIMELINE_SUMMARY)
    _activity(run_id, TIMELINE_SUMMARY, "Reconstructing the chronological record and writing the evidence-backed summary.", "RUNNING")
    timeline_ctx = ToolContext(run_id=run_id, patient_id=patient_id, agent=TIMELINE_SUMMARY)
    timeline_result, timeline_error = _with_retry(TIMELINE_SUMMARY, run_id, "timeline build", lambda: agent_tools.build_patient_timeline(timeline_ctx))
    if timeline_error or not timeline_result:
        failures.append(f"Timeline generation failed: {timeline_error}")
        _activity(run_id, TIMELINE_SUMMARY, f"Timeline generation failed: {timeline_error}", "FAILED")
        metrics["timeline_events"] = 0
    else:
        metrics["timeline_events"] = timeline_result.get("count", 0)

    summary_result, summary_error = _with_retry(TIMELINE_SUMMARY, run_id, "summary generation", lambda: agent_tools.generate_patient_summary(timeline_ctx))
    if summary_error or not summary_result:
        failures.append(f"Summary generation failed: {summary_error}")
        _activity(run_id, TIMELINE_SUMMARY, f"Summary generation failed: {summary_error}", "FAILED")
    _activity(
        run_id,
        TIMELINE_SUMMARY,
        f"{metrics.get('timeline_events', 0)} timeline event(s) and the patient summary are stored.",
        "COMPLETED" if not (timeline_error or summary_error) else "FAILED",
    )

    # -------------------------------------------------- 6. final quality check
    repository.update_run(run_id, current_agent=ORCHESTRATOR)
    quality_issues = _quality_check(patient_id)
    warnings.extend(quality_issues)
    if ocr_documents:
        warnings.append(
            "Pages without extractable text were marked OCR_REQUIRED: " + ", ".join(sorted(set(ocr_documents)))
        )

    # ------------------------------- 7. optional model-driven coordination layer
    engine = "deterministic"
    llm = sdk_runtime.run_coordinator(patient_id, run_id, focus=focus)
    if llm.get("available"):
        engine = "deterministic+agents_sdk"
        _activity(
            run_id,
            ORCHESTRATOR,
            "Coordinator reviewed the stored evidence with the Agents SDK.",
            "COMPLETED",
            detail={"note": llm.get("note", ""), "tool_calls": llm.get("tool_calls", 0)},
        )
    elif settings.llm_enabled:
        warnings.append(f"Model layer unavailable: {llm.get('reason', 'unknown error')}")
    else:
        _activity(run_id, ORCHESTRATOR, f"Model layer disabled: {llm.get('reason', '')}", "SKIPPED")

    status = "COMPLETED"
    if failures and (not timeline_result and not summary_result):
        status = "FAILED"
    elif failures:
        status = "PARTIAL"

    metrics["conflicts_verified"] = verification_counts.get("VERIFIED_POTENTIAL_CONFLICT", 0)
    metrics["conflicts_rejected"] = verification_counts.get("NOT_A_CONFLICT", 0)
    metrics["conflicts_needing_review"] = len(
        [item for item in repository.list_conflicts(patient_id) if item.get("review_status") == "PENDING"]
    )
    metrics["documents"] = len(documents)

    repository.update_run(
        run_id,
        status=status,
        current_agent=None,
        engine=engine,
        completed_at=utc_now(),
        warnings=warnings,
        metrics=metrics,
        error_message="; ".join(failures) if failures else None,
    )
    repository.log_audit(patient_id, "orchestrator", "ANALYSIS_COMPLETED", {"run_id": run_id, "status": status, "metrics": metrics})
    _activity(run_id, ORCHESTRATOR, f"Workflow {status.lower()} with {len(warnings)} warning(s).", status)

    return {
        "run_id": run_id,
        "status": status,
        "engine": engine,
        "metrics": metrics,
        "warnings": warnings,
        "failures": failures,
    }


def _quality_check(patient_id: str) -> list[str]:
    """Deterministic checks that protect against fabricated or dangling references."""
    issues: list[str] = []
    documents = {doc["id"]: doc for doc in repository.list_documents(patient_id)}
    for entity in repository.list_entities(patient_id):
        document_id = entity.get("source_document_id")
        if document_id and document_id not in documents:
            issues.append(f"Entity {entity.get('id')} references an unknown document {document_id}.")
            continue
        page = entity.get("source_page")
        if document_id and page is not None and not repository.get_page(document_id, page):
            issues.append(f"Entity {entity.get('id')} cites page {page}, which does not exist in its document.")
        if not entity.get("evidence_snippet"):
            issues.append(f"Entity {entity.get('id')} has no supporting snippet.")

    for conflict in repository.list_conflicts(patient_id):
        references = conflict.get("source_references") or []
        if len(references) < 2:
            issues.append(f"Conflict {conflict.get('id')} cites fewer than two sources.")
        if conflict.get("verification_status") == "UNVERIFIED":
            issues.append(f"Conflict {conflict.get('id')} is displayed without verification.")

    events = repository.list_timeline(patient_id)
    dated = [event for event in events if event.get("event_date")]
    if [event["event_date"] for event in dated] != sorted(event["event_date"] for event in dated):
        issues.append("Timeline events are not in chronological order.")
    for event in events:
        document_id = event.get("source_document_id")
        if document_id and document_id not in documents:
            issues.append(f"Timeline event {event.get('id')} references an unknown document.")
    return issues

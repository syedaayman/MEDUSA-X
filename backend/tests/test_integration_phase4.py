"""Integration tests for the Phase 4 hardening: conflict/evidence round-trip,
multi-document timeline, analysis activity API, and verified_at persistence.

All tests run against the isolated test database (see conftest.py) and require no
OpenAI credentials.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest

from backend import repository
from backend.db import init_db

TERMINAL = {"COMPLETED", "PARTIAL", "FAILED"}


def make_pdf(*pages):
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    for lines in pages:
        page = document.new_page()
        y = 72
        for line in lines:
            page.insert_text((72, y), line, fontsize=10)
            y += 16
    blob = document.tobytes()
    document.close()
    return blob


def upload(client, patient_id, files, start_analysis=True):
    return client.post(
        "/api/upload",
        data={
            "patient_id": patient_id,
            "display_name": "Test Patient",
            "start_analysis": "true" if start_analysis else "false",
            "reprocess": "false",
        },
        files=[("files", (name, blob, "application/pdf")) for name, blob in files],
    )


def wait_for_run(client, run_id, timeout=90.0):
    deadline = time.time() + timeout
    body = {}
    while time.time() < deadline:
        response = client.get(f"/api/analysis/{run_id}")
        assert response.status_code == 200, response.text
        body = response.json()
        if str(body.get("status", "")).upper() in TERMINAL:
            return body
        time.sleep(0.2)
    pytest.fail(f"analysis run {run_id} did not finish: {body}")


DOC_A = [
    "Discharge Summary",
    "Patient: Test Patient",
    "Date: 2024-03-01",
    "Diagnosis: Type 2 diabetes mellitus",
    "Medications:",
    "- Metformin 500 mg twice daily",
    "Allergy: Penicillin",
]

DOC_B = [
    "Prescription",
    "Patient: Test Patient",
    "Date: 2024-03-01",
    "Medications:",
    "- Metformin 1000 mg twice daily",
]

LATER = [
    "Consultation Note",
    "Patient: Test Patient",
    "Date: 2024-07-15",
    "Diagnosis: Hypertension",
    "Medications:",
    "- Amlodipine 5 mg once daily",
]


# ---------------------------------------------------------------------------
# 1. Conflict + evidence API round trip
# ---------------------------------------------------------------------------
def test_conflict_and_evidence_api_round_trip(client, patient_id):
    response = upload(client, patient_id, [("discharge.pdf", make_pdf(DOC_A)), ("prescription.pdf", make_pdf(DOC_B))])
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["documents"]) == 2
    run = wait_for_run(client, body["analysis_run_id"])
    assert run["status"] in {"COMPLETED", "PARTIAL"}, run

    conflicts = client.get(f"/api/patient/{patient_id}/conflicts").json()
    assert isinstance(conflicts, list) and conflicts, "expected at least one conflict"
    medication = [row for row in conflicts if str(row.get("category", "")).upper() == "MEDICATION"]
    assert medication, f"no medication conflict stored: {json.dumps(conflicts)[:500]}"
    conflict = medication[0]

    # IDs are exposed under both spellings
    assert conflict.get("id") and conflict.get("conflict_id")
    assert conflict["id"] == conflict["conflict_id"]
    assert conflict.get("verification_status") in {
        "VERIFIED_POTENTIAL_CONFLICT",
        "NOT_A_CONFLICT",
        "INSUFFICIENT_EVIDENCE",
        "NEEDS_HUMAN_REVIEW",
        "PENDING_VERIFICATION",
    }
    assert conflict.get("source_references"), "conflict must cite source references"
    docs = {ref.get("document_id") for ref in conflict["source_references"] if isinstance(ref, dict)}
    assert len({d for d in docs if d}) >= 2, "both documents must be cited"
    assert any("metformin" in (ref.get("snippet") or "").lower() for ref in conflict["source_references"])
    serialised = json.dumps(conflict).lower()
    assert "500" in serialised and "1000" in serialised

    # Evidence endpoint returns the original page text for both sides
    evidence = client.get(f"/api/conflicts/{conflict['id']}/evidence")
    assert evidence.status_code == 200, evidence.text
    payload = evidence.json()
    assert payload.get("conflict_id") == conflict["id"]
    references = payload.get("references") or []
    assert len(references) >= 2
    for ref in references:
        assert ref.get("available") is True, ref
        assert ref.get("page_text") and "metformin" in ref["page_text"].lower(), ref
        assert ref.get("snippet") and "metformin" in ref["snippet"].lower(), ref
        assert ref.get("page") is not None and int(ref["page"]) >= 1


# ---------------------------------------------------------------------------
# 2. Multi-document timeline ordering and provenance
# ---------------------------------------------------------------------------
def test_multi_document_timeline_ordering_and_provenance(client, patient_id):
    response = upload(client, patient_id, [("discharge.pdf", make_pdf(DOC_A)), ("consult.pdf", make_pdf(LATER))])
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["documents"]) == 2
    uploaded = {doc.get("id") or doc.get("document_id") for doc in body["documents"]}
    run = wait_for_run(client, body["analysis_run_id"])
    assert run["status"] in {"COMPLETED", "PARTIAL"}, run

    timeline = client.get(f"/api/patient/{patient_id}/timeline")
    assert timeline.status_code == 200, timeline.text
    events = timeline.json()
    assert events, "timeline must contain events for multiple documents"

    referenced = {event.get("source_document_id") for event in events if event.get("source_document_id")}
    assert referenced, "timeline events must cite a source document"
    assert referenced.issubset(uploaded), (referenced, uploaded)

    for event in events:
        assert event.get("event_id"), "event_id must be present"
        if event.get("source_document_id"):
            assert event.get("source_page") is None or int(event["source_page"]) >= 1

    dated = [event["event_date"] for event in events if event.get("event_date")]
    assert dated == sorted(dated), "timeline must be chronologically ordered"


# ---------------------------------------------------------------------------
# 3. Analysis activity API
# ---------------------------------------------------------------------------
def test_analysis_activity_api_persisted_and_ordered(client, patient_id):
    response = upload(client, patient_id, [("discharge.pdf", make_pdf(DOC_A))])
    assert response.status_code == 200, response.text
    body = response.json()
    run_id = body["analysis_run_id"]
    run = wait_for_run(client, run_id)
    assert run["status"] in {"COMPLETED", "PARTIAL"}, run

    activity = client.get(f"/api/analysis/{run_id}/activity")
    assert activity.status_code == 200, activity.text
    entries = activity.json()
    assert isinstance(entries, list) and entries, "activity must be persisted"

    # Ordering is by created_at (then rowid); timestamps must be non-decreasing.
    timestamps = [entry.get("created_at") for entry in entries if entry.get("created_at")]
    assert timestamps == sorted(timestamps), "activity must be in creation order"

    statuses = {str(entry.get("status", "")).upper() for entry in entries}
    assert statuses.issubset({"QUEUED", "RUNNING", "COMPLETED", "FAILED", "NEEDS_REVIEW", "SKIPPED", "PARTIAL"}), statuses
    assert any(str(entry.get("agent_name", "")).upper() == "ORCHESTRATOR" for entry in entries)
    assert any(str(entry.get("agent_name", "")).upper() == "CLINICAL_STRUCTURING" for entry in entries)
    # At least one tool call activity should be recorded.
    assert any(entry.get("activity_type") == "TOOL_CALL" for entry in entries)

    # Unknown run id must 404.
    assert client.get("/api/analysis/does-not-exist/activity").status_code == 404


# ---------------------------------------------------------------------------
# 4. verified_at persistence (Objective 2)
# ---------------------------------------------------------------------------
def test_verified_at_populated_and_persisted(client, patient_id):
    response = upload(client, patient_id, [("discharge.pdf", make_pdf(DOC_A)), ("prescription.pdf", make_pdf(DOC_B))])
    assert response.status_code == 200, response.text
    body = response.json()
    run = wait_for_run(client, body["analysis_run_id"])
    assert run["status"] in {"COMPLETED", "PARTIAL"}, run

    conflicts = client.get(f"/api/patient/{patient_id}/conflicts").json()
    assert conflicts, "expected at least one conflict"
    for conflict in conflicts:
        assert conflict.get("verified_at"), f"verified_at missing after verification: {conflict.get('conflict_id')}"
        first = conflict["verified_at"]

    # Re-fetch and confirm the timestamp persisted unchanged.
    conflicts2 = client.get(f"/api/patient/{patient_id}/conflicts").json()
    assert conflicts2 and conflicts2[0].get("verified_at") == first

    # Single-conflict endpoint must agree.
    single = client.get(f"/api/conflicts/{conflicts[0]['id']}")
    assert single.status_code == 200, single.text
    assert single.json().get("verified_at") == first


def test_unverified_conflict_has_no_verified_at():
    """A conflict inserted directly (never run through verification) keeps verified_at None."""
    init_db()
    pid = f"test-unverified-{uuid.uuid4().hex[:8]}"
    repository.ensure_patient(pid)
    raw_id = f"cfl_{uuid.uuid4().hex[:8]}"
    repository.save_conflict(
        pid,
        {
            "id": raw_id,
            "patient_id": pid,
            "category": "MEDICATION",
            "description": "Unverified conflict",
            "compared_entity_ids": [],
            "compared_values": [],
            "source_references": [],
            "reason": "test",
            "severity": "MEDIUM",
            "confidence": 0.5,
            "verification_status": "UNVERIFIED",
            "review_status": "PENDING",
            "data_origin": "USER_UPLOAD",
        },
    )
    stored = repository.get_conflict(raw_id)
    assert stored is not None
    assert stored.get("verified_at") is None, stored

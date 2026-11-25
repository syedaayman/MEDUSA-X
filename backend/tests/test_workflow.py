"""End-to-end API tests for the MEDUSA-X agentic workflow.

Every test runs against an isolated SQLite database and document store
(see conftest.py) with no OpenAI key, so the deterministic evidence pipeline is
exercised exactly as it runs in a fresh checkout.
"""

from __future__ import annotations

import json
import time

import pytest

TERMINAL = {"COMPLETED", "PARTIAL", "FAILED"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def make_pdf(*pages: list[str]) -> bytes:
    """Build a small real PDF (PyMuPDF) so ingestion parses genuine page text."""
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


def upload(client, patient_id: str, files: list[tuple[str, bytes]], start_analysis: bool = True):
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


def doc_id(document: dict) -> str:
    return document.get("id") or document.get("document_id") or ""


def wait_for_run(client, run_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        response = client.get(f"/api/analysis/{run_id}")
        assert response.status_code == 200, response.text
        body = response.json()
        if str(body.get("status", "")).upper() in TERMINAL:
            return body
        time.sleep(0.2)
    pytest.fail(f"analysis run {run_id} did not reach a terminal status: {body}")


def items(payload, *keys):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys or ("items", "results", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def activity_of(client, run_id: str) -> list[dict]:
    response = client.get(f"/api/analysis/{run_id}/activity")
    assert response.status_code == 200, response.text
    return items(response.json(), "activity", "events")


# --------------------------------------------------------------------------- #
# fixtures for the documents used across tests
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Test 1 - single uploaded document
# --------------------------------------------------------------------------- #
def test_single_document_extracts_and_builds_timeline_without_inventing_conflicts(client, patient_id):
    response = upload(client, patient_id, [("discharge.pdf", make_pdf(DOC_A))])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["documents"], body
    document = body["documents"][0]
    assert document["page_count"] == 1
    assert document["processing_status"] in {"PROCESSED", "EXTRACTED", "OCR_REQUIRED", "COMPLETED"}

    run_id = body.get("analysis_run_id")
    assert run_id, "upload should start an analysis run"
    run = wait_for_run(client, run_id)
    assert run["status"] in {"COMPLETED", "PARTIAL"}, run

    entities = client.get(f"/api/patient/{patient_id}/entities").json()
    entity_rows = items(entities, "entities")
    assert entity_rows, "clinical structuring should extract at least one entity"
    assert all(row.get("source_document_id") or row.get("document_id") for row in entity_rows)

    timeline = items(client.get(f"/api/patient/{patient_id}/timeline").json(), "events")
    assert timeline, "a single document must still produce timeline events"

    conflicts = items(client.get(f"/api/patient/{patient_id}/conflicts").json(), "conflicts")
    assert conflicts == [], "one document cannot produce cross-document conflicts"


# --------------------------------------------------------------------------- #
# Test 2 - multiple documents share patient context
# --------------------------------------------------------------------------- #
def test_multiple_documents_share_patient_context_and_keep_sources(client, patient_id):
    later = [
        "Consultation Note",
        "Patient: Test Patient",
        "Date: 2024-07-15",
        "Diagnosis: Hypertension",
        "Medications:",
        "- Amlodipine 5 mg once daily",
    ]
    response = upload(
        client,
        patient_id,
        [("discharge.pdf", make_pdf(DOC_A)), ("consult.pdf", make_pdf(later))],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["documents"]) == 2
    uploaded = {doc_id(document) for document in body["documents"]}

    run = wait_for_run(client, body["analysis_run_id"])
    assert run["status"] in {"COMPLETED", "PARTIAL"}, run

    timeline = items(client.get(f"/api/patient/{patient_id}/timeline").json(), "events")
    assert timeline
    referenced = {event.get("source_document_id") for event in timeline if event.get("source_document_id")}
    assert referenced, "timeline events must cite their source document"
    assert referenced.issubset(uploaded)

    for event in timeline:
        if event.get("source_document_id"):
            assert event.get("source_page") is None or int(event["source_page"]) >= 1

    dated = [event["event_date"] for event in timeline if event.get("event_date")]
    assert dated == sorted(dated), "timeline must be ordered chronologically"


# --------------------------------------------------------------------------- #
# Test 3 - medication discrepancy is proposed and independently verified
# --------------------------------------------------------------------------- #
def test_medication_discrepancy_is_verified_against_both_sources(client, patient_id):
    response = upload(
        client,
        patient_id,
        [("discharge.pdf", make_pdf(DOC_A)), ("prescription.pdf", make_pdf(DOC_B))],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    run = wait_for_run(client, body["analysis_run_id"])
    assert run["status"] in {"COMPLETED", "PARTIAL"}, run

    conflicts = items(client.get(f"/api/patient/{patient_id}/conflicts").json(), "conflicts")
    medication = [row for row in conflicts if str(row.get("category", "")).upper() == "MEDICATION"]
    assert medication, f"expected a medication discrepancy, stored conflicts: {json.dumps(conflicts)[:800]}"

    conflict = medication[0]
    serialised = json.dumps(conflict)
    assert "500" in serialised and "1000" in serialised, serialised[:800]

    references = conflict.get("source_references") or []
    documents = {
        ref.get("document_id") or ref.get("source_document_id")
        for ref in references
        if isinstance(ref, dict)
    }
    assert len({item for item in documents if item}) >= 2, "both documents must be cited"

    assert conflict.get("verification_status"), "the verification agent must record a decision"
    assert conflict.get("verification_status") != "VERIFIED_POTENTIAL_CONFLICT" or conflict.get(
        "requires_human_review", True
    )

    lowered = json.dumps(conflict).lower()
    assert "is correct" not in lowered and "the correct dose is" not in lowered

    evidence = client.get(f"/api/conflicts/{conflict['id']}/evidence")
    assert evidence.status_code == 200, evidence.text
    assert "metformin" in evidence.text.lower(), "evidence viewer must return the original page text"


# --------------------------------------------------------------------------- #
# Test 4 - a legitimate dose change over time is not called a contradiction
# --------------------------------------------------------------------------- #
def test_dose_change_over_time_is_not_flagged_as_high_severity_conflict(client, patient_id):
    earlier = [
        "Prescription",
        "Patient: Test Patient",
        "Date: 2024-01-10",
        "Medications:",
        "- Metformin 500 mg twice daily",
    ]
    later = [
        "Prescription",
        "Patient: Test Patient",
        "Date: 2024-06-20",
        "Medications:",
        "- Metformin 1000 mg twice daily",
    ]
    response = upload(
        client,
        patient_id,
        [("jan.pdf", make_pdf(earlier)), ("jun.pdf", make_pdf(later))],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    wait_for_run(client, body["analysis_run_id"])

    conflicts = items(client.get(f"/api/patient/{patient_id}/conflicts").json(), "conflicts")
    for conflict in conflicts:
        assert not (
            str(conflict.get("severity", "")).upper() == "HIGH"
            and conflict.get("verification_status") == "VERIFIED_POTENTIAL_CONFLICT"
        ), f"a chronological dose change was reported as a high-severity conflict: {json.dumps(conflict)[:600]}"


# --------------------------------------------------------------------------- #
# Test 5 - unsupported findings are rejected, not displayed as verified
# --------------------------------------------------------------------------- #
def test_verifier_rejects_a_finding_without_resolvable_evidence(client, patient_id):
    from backend.clinical import verifier

    fabricated = {
        "id": "conflict-fabricated",
        "patient_id": patient_id,
        "category": "MEDICATION",
        "compared_entity_ids": ["entity-does-not-exist-1", "entity-does-not-exist-2"],
        "compared_values": [{"value": "500 mg"}, {"value": "1000 mg"}],
        "source_references": [],
    }
    result = verifier.verify_conflict(patient_id, fabricated)
    assert result["decision"] in {"INSUFFICIENT_EVIDENCE", "NEEDS_HUMAN_REVIEW", "NOT_A_CONFLICT"}
    assert result["decision"] != "VERIFIED_POTENTIAL_CONFLICT"


# --------------------------------------------------------------------------- #
# Test 6 - duplicate uploads do not duplicate records or events
# --------------------------------------------------------------------------- #
def test_duplicate_upload_is_detected(client, patient_id):
    blob = make_pdf(DOC_A)
    first = upload(client, patient_id, [("discharge.pdf", blob)], start_analysis=False)
    assert first.status_code == 200, first.text
    assert first.json()["documents"][0].get("duplicate") in (False, None)

    second = upload(client, patient_id, [("discharge-copy.pdf", blob)], start_analysis=False)
    assert second.status_code == 200, second.text
    assert second.json()["documents"][0].get("duplicate") is True

    documents = items(client.get(f"/api/patient/{patient_id}/documents").json(), "documents")
    assert len(documents) == 1, f"duplicate upload created extra records: {documents}"


# --------------------------------------------------------------------------- #
# Test 7 - invalid files are rejected gracefully
# --------------------------------------------------------------------------- #
def test_invalid_pdf_is_rejected_without_crashing(client, patient_id):
    response = upload(client, patient_id, [("broken.pdf", b"this is not a pdf")])
    assert 400 <= response.status_code < 500, response.text
    assert client.get("/health").status_code == 200, "the API must stay healthy after a bad upload"

    empty = client.post(
        "/api/upload",
        data={"patient_id": "", "start_analysis": "false"},
        files=[("files", ("x.pdf", make_pdf(DOC_A), "application/pdf"))],
    )
    assert 400 <= empty.status_code < 500, "an empty patient id must be rejected"


# --------------------------------------------------------------------------- #
# Test 8 - missing API key is reported, deterministic mode still works
# --------------------------------------------------------------------------- #
def test_missing_api_key_is_reported_but_pipeline_still_runs(client, patient_id):
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    flags = {
        key: value
        for key, value in body.items()
        if isinstance(value, bool) and ("llm" in key or "model" in key or "openai" in key)
    }
    assert flags, f"health must report whether the model layer is configured: {body}"
    assert not any(flags.values()), f"no key is configured, yet health claims a model layer: {flags}"

    response = upload(client, patient_id, [("discharge.pdf", make_pdf(DOC_A))])
    assert response.status_code == 200, response.text
    run = wait_for_run(client, response.json()["analysis_run_id"])
    assert run["status"] in {"COMPLETED", "PARTIAL"}, run


# --------------------------------------------------------------------------- #
# Test 9 - a failing specialist is recorded and the workflow still terminates
# --------------------------------------------------------------------------- #
def test_specialist_failure_is_recorded_and_run_terminates(client, patient_id, monkeypatch):
    from backend.agents import orchestrator
    from backend.agents import tools as agent_tools

    def boom(*args, **kwargs):
        raise RuntimeError("simulated specialist failure")

    patched = []
    for module in (agent_tools, orchestrator):
        if hasattr(module, "classify_document"):
            monkeypatch.setattr(module, "classify_document", boom, raising=False)
            patched.append(module.__name__)
    if not patched:
        pytest.skip("classify_document is not exposed as a patchable tool symbol")

    first = upload(client, patient_id, [("discharge.pdf", make_pdf(DOC_A))], start_analysis=False)
    assert first.status_code == 200, first.text

    started = client.post(f"/api/patient/{patient_id}/process")
    assert started.status_code in (200, 202), started.text
    run = wait_for_run(client, started.json()["analysis_run_id"])

    assert run["status"] in TERMINAL, run
    activity = activity_of(client, run["id"])
    failed = [
        entry
        for entry in activity
        if str(entry.get("status", "")).upper() in {"FAILED", "ERROR"}
        or "fail" in str(entry.get("activity_message", "")).lower()
        or "error" in str(entry.get("activity_message", "")).lower()
    ]
    assert failed or run["status"] in {"PARTIAL", "FAILED"}, (
        f"specialist failure was not recorded: status={run['status']} activity={json.dumps(activity)[:600]}"
    )


# --------------------------------------------------------------------------- #
# Test 10 - human review decisions persist and are audited
# --------------------------------------------------------------------------- #
def test_human_review_decision_persists_and_is_audited(client, patient_id):
    response = upload(
        client,
        patient_id,
        [("discharge.pdf", make_pdf(DOC_A)), ("prescription.pdf", make_pdf(DOC_B))],
    )
    assert response.status_code == 200, response.text
    wait_for_run(client, response.json()["analysis_run_id"])

    conflicts = items(client.get(f"/api/patient/{patient_id}/conflicts").json(), "conflicts")
    if not conflicts:
        pytest.skip("no discrepancy detected for this fixture, nothing to review")
    conflict_id = conflicts[0]["id"]

    updated = client.patch(
        f"/api/conflicts/{conflict_id}/review",
        json={"review_status": "REVIEWED", "reviewer_note": "Checked both source pages.", "actor": "test-reviewer"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json().get("review_status") == "REVIEWED"

    refreshed = items(client.get(f"/api/patient/{patient_id}/conflicts").json(), "conflicts")
    stored = next(row for row in refreshed if row["id"] == conflict_id)
    assert stored["review_status"] == "REVIEWED"
    assert stored.get("reviewer_note") == "Checked both source pages."

    audit = client.get(f"/api/patient/{patient_id}/audit")
    assert audit.status_code == 200, audit.text
    assert "reviewed" in audit.text.lower()

    invalid = client.patch(
        f"/api/conflicts/{conflict_id}/review", json={"review_status": "NOT_A_STATUS"}
    )
    assert 400 <= invalid.status_code < 500, "invalid review statuses must be rejected"


# --------------------------------------------------------------------------- #
# Test 11 - the evidence-backed summary is available and clearly labelled
# --------------------------------------------------------------------------- #
def test_summary_is_evidence_backed_and_marked_as_prototype(client, patient_id):
    response = upload(client, patient_id, [("discharge.pdf", make_pdf(DOC_A))])
    assert response.status_code == 200, response.text
    wait_for_run(client, response.json()["analysis_run_id"])

    summary = client.get(f"/api/patient/{patient_id}/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert isinstance(body, dict) and body, body

    serialised = json.dumps(body).lower()
    assert "metformin" in serialised or "diabetes" in serialised, "summary must reflect the source record"
    assert "disclaimer" in serialised or "review" in serialised, "summary must carry a review disclaimer"


# --------------------------------------------------------------------------- #
# Test 12 - patient isolation for dataset records
# --------------------------------------------------------------------------- #
def test_dataset_patients_never_appear_as_uploaded_patients(client, patient_id):
    from backend import repository

    upload(client, patient_id, [("discharge.pdf", make_pdf(DOC_A))], start_analysis=False)
    repository.ensure_patient("synthea:0000-test", data_origin="SYNTHETIC_DATASET")

    listed = items(client.get("/api/patients").json(), "patients")
    identifiers = {row.get("id") for row in listed}
    assert patient_id in identifiers
    assert not any(str(identifier).startswith("synthea:") for identifier in identifiers), listed

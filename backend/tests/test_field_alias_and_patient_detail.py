"""Integration tests: repository field aliases, API serialization, and patient-detail endpoints.

These tests verify the fix for the event_id / conflict_id schema mismatch.
All tests run against an isolated in-memory database via the shared conftest fixture.
The user's local SQLite database is NEVER touched.
"""

from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pid() -> str:
    """Return a unique patient ID for each test call."""
    return f"test-alias-{uuid.uuid4().hex[:8]}"


def _make_patient(client, patient_id: str) -> dict:
    """Create a patient via the upload endpoint using a minimal in-memory PDF."""
    import io
    import struct
    # Minimal valid PDF bytes (1-page, no content)
    minimal_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n"
        b"0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF\n"
    )
    response = client.post(
        "/api/upload",
        data={"patient_id": patient_id, "start_analysis": "false"},
        files={"files": ("test.pdf", io.BytesIO(minimal_pdf), "application/pdf")},
    )
    return response


# ---------------------------------------------------------------------------
# A. Repository-layer field alias tests (no HTTP layer)
# ---------------------------------------------------------------------------

class TestRepositoryAliases:
    """Verify that list_timeline / list_conflicts / get_conflict inject the alias fields."""

    def test_list_timeline_injects_event_id(self):
        """list_timeline must return dicts containing both 'id' and 'event_id'."""
        from backend import repository
        from backend.db import init_db

        init_db()
        pid = _pid()
        repository.ensure_patient(pid)

        # Save a minimal timeline event
        repository.save_timeline(pid, [
            {
                "event_id": "evt_test_001",
                "patient_id": pid,
                "category": "DIAGNOSIS",
                "description": "Test diagnosis",
                "event_date": "2025-01-01",
                "date_precision": "DAY",
                "verification_status": "UNVERIFIED",
                "data_origin": "USER_UPLOAD",
            }
        ])

        events = repository.list_timeline(pid)
        assert len(events) == 1
        event = events[0]
        # Both keys must be present
        assert "id" in event, "DB column 'id' must be present"
        assert "event_id" in event, "Alias 'event_id' must be injected by list_timeline"
        # They must refer to the same value
        assert event["id"] == event["event_id"]

    def test_list_timeline_empty_returns_empty_list(self):
        from backend import repository
        from backend.db import init_db

        init_db()
        pid = _pid()
        repository.ensure_patient(pid)
        events = repository.list_timeline(pid)
        assert events == []

    def test_list_conflicts_injects_conflict_id(self):
        """list_conflicts must return dicts containing both 'id' and 'conflict_id'."""
        from backend import repository
        from backend.db import init_db

        init_db()
        pid = _pid()
        repository.ensure_patient(pid)

        conflict = {
            "id": f"cfl_{uuid.uuid4().hex[:8]}",
            "patient_id": pid,
            "category": "MEDICATION",
            "description": "Test conflict",
            "compared_entity_ids": [],
            "compared_values": [],
            "source_references": [],
            "reason": "Test reason",
            "severity": "HIGH",
            "confidence": 0.7,
            "verification_status": "PENDING_VERIFICATION",
            "review_status": "NOT_REQUIRED",
            "data_origin": "USER_UPLOAD",
        }
        repository.save_conflict(pid, conflict)

        conflicts = repository.list_conflicts(pid)
        assert len(conflicts) == 1
        c = conflicts[0]
        assert "id" in c, "DB column 'id' must be present"
        assert "conflict_id" in c, "Alias 'conflict_id' must be injected by list_conflicts"
        assert c["id"] == c["conflict_id"]

    def test_list_conflicts_empty_returns_empty_list(self):
        from backend import repository
        from backend.db import init_db

        init_db()
        pid = _pid()
        repository.ensure_patient(pid)
        conflicts = repository.list_conflicts(pid)
        assert conflicts == []

    def test_get_conflict_injects_conflict_id(self):
        """get_conflict must also inject the conflict_id alias."""
        from backend import repository
        from backend.db import init_db

        init_db()
        pid = _pid()
        repository.ensure_patient(pid)

        raw_id = f"cfl_{uuid.uuid4().hex[:8]}"
        conflict = {
            "id": raw_id,
            "patient_id": pid,
            "category": "ALLERGY",
            "description": "Allergy conflict",
            "compared_entity_ids": [],
            "compared_values": [],
            "source_references": [],
            "reason": "Different allergy records",
            "severity": "HIGH",
            "confidence": 0.65,
            "verification_status": "PENDING_VERIFICATION",
            "review_status": "NOT_REQUIRED",
            "data_origin": "USER_UPLOAD",
        }
        repository.save_conflict(pid, conflict)

        fetched = repository.get_conflict(raw_id)
        assert fetched is not None
        assert "conflict_id" in fetched, "get_conflict must inject conflict_id alias"
        assert fetched["conflict_id"] == fetched["id"]


# ---------------------------------------------------------------------------
# B. API serialization tests (HTTP layer with Pydantic validation)
# ---------------------------------------------------------------------------

class TestTimelineAPI:
    """GET /api/patient/{id}/timeline must return 200 with valid TimelineEvent objects."""

    def test_timeline_empty_returns_200_empty_list(self, client, patient_id):
        """A patient with no timeline events should return 200 with []."""
        from backend import repository
        from backend.db import init_db

        init_db()
        repository.ensure_patient(patient_id, display_name="Timeline Empty Test")

        response = client.get(f"/api/patient/{patient_id}/timeline")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        assert data == []

    def test_timeline_with_saved_events_returns_event_id(self, client, patient_id):
        """Timeline events returned by the API must contain event_id (Pydantic required field)."""
        from backend import repository
        from backend.db import init_db

        init_db()
        # Ensure the patient exists in the DB
        repository.ensure_patient(patient_id)

        repository.save_timeline(patient_id, [
            {
                "event_id": f"evt_{uuid.uuid4().hex[:8]}",
                "patient_id": patient_id,
                "category": "MEDICATION",
                "description": "Aspirin 100mg",
                "event_date": "2025-03-15",
                "date_precision": "DAY",
                "verification_status": "SUPPORTED",
                "data_origin": "USER_UPLOAD",
            },
            {
                "event_id": f"evt_{uuid.uuid4().hex[:8]}",
                "patient_id": patient_id,
                "category": "DIAGNOSIS",
                "description": "Hypertension",
                "event_date": "2025-01-10",
                "date_precision": "DAY",
                "verification_status": "UNVERIFIED",
                "data_origin": "USER_UPLOAD",
            },
        ])

        response = client.get(f"/api/patient/{patient_id}/timeline")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        events = response.json()
        assert len(events) == 2

        for event in events:
            assert "event_id" in event, f"event_id missing from API response: {event}"
            assert event["event_id"], "event_id must be non-empty"
            assert "category" in event
            assert "description" in event


class TestConflictsAPI:
    """GET /api/patient/{id}/conflicts must return 200 with valid ConflictProposal objects."""

    def test_conflicts_empty_returns_200_empty_list(self, client, patient_id):
        from backend import repository
        from backend.db import init_db

        init_db()
        repository.ensure_patient(patient_id)

        response = client.get(f"/api/patient/{patient_id}/conflicts")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.json() == []

    def test_conflicts_with_saved_data_returns_conflict_id(self, client, patient_id):
        """Conflict records returned by API must contain conflict_id (Pydantic required field)."""
        from backend import repository
        from backend.db import init_db

        init_db()
        repository.ensure_patient(patient_id)

        raw_id = f"cfl_{uuid.uuid4().hex[:8]}"
        repository.save_conflict(patient_id, {
            "id": raw_id,
            "patient_id": patient_id,
            "category": "MEDICATION",
            "description": "Metformin dose discrepancy",
            "compared_entity_ids": [],
            "compared_values": ["500mg", "1000mg"],
            "source_references": [],
            "reason": "Same-day documents show different doses",
            "possible_explanation": "Titration or transcription error",
            "severity": "HIGH",
            "confidence": 0.72,
            "verification_status": "PENDING_VERIFICATION",
            "review_status": "NOT_REQUIRED",
            "requires_human_review": True,
            "data_origin": "USER_UPLOAD",
        })

        response = client.get(f"/api/patient/{patient_id}/conflicts")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        conflicts = response.json()
        assert len(conflicts) == 1

        conflict = conflicts[0]
        assert "conflict_id" in conflict, f"conflict_id missing from API response: {conflict}"
        assert conflict["conflict_id"] == raw_id
        assert conflict["category"] == "MEDICATION"


class TestConflictReviewAPI:
    """PATCH /api/conflicts/{id}/review must return 200 with updated ConflictProposal."""

    def test_review_endpoint_returns_conflict_id(self, client, patient_id):
        from backend import repository
        from backend.db import init_db

        init_db()
        repository.ensure_patient(patient_id)

        raw_id = f"cfl_{uuid.uuid4().hex[:8]}"
        repository.save_conflict(patient_id, {
            "id": raw_id,
            "patient_id": patient_id,
            "category": "DIAGNOSIS",
            "description": "Diabetes status conflict",
            "compared_entity_ids": [],
            "compared_values": ["CURRENT", "HISTORICAL"],
            "source_references": [],
            "reason": "Same-date documents disagree on status",
            "severity": "MEDIUM",
            "confidence": 0.6,
            "verification_status": "VERIFIED_POTENTIAL_CONFLICT",
            "review_status": "PENDING",
            "requires_human_review": True,
            "data_origin": "USER_UPLOAD",
        })

        response = client.patch(
            f"/api/conflicts/{raw_id}/review",
            json={"review_status": "REVIEWED", "reviewer_note": "Confirmed historical in prior discharge notes."},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        assert "conflict_id" in result, f"conflict_id missing from review response: {result}"
        assert result["conflict_id"] == raw_id
        assert result["review_status"] == "REVIEWED"
        assert result["reviewer_note"] == "Confirmed historical in prior discharge notes."

    def test_review_endpoint_invalid_status_returns_422(self, client, patient_id):
        from backend import repository
        from backend.db import init_db

        init_db()
        repository.ensure_patient(patient_id)

        raw_id = f"cfl_{uuid.uuid4().hex[:8]}"
        repository.save_conflict(patient_id, {
            "id": raw_id,
            "patient_id": patient_id,
            "category": "ALLERGY",
            "description": "Allergy conflict",
            "compared_entity_ids": [],
            "compared_values": [],
            "source_references": [],
            "reason": "Test",
            "severity": "HIGH",
            "confidence": 0.5,
            "verification_status": "PENDING_VERIFICATION",
            "review_status": "PENDING",
            "data_origin": "USER_UPLOAD",
        })

        response = client.patch(
            f"/api/conflicts/{raw_id}/review",
            json={"review_status": "INVALID_STATUS"},
        )
        assert response.status_code == 422

    def test_review_endpoint_unknown_conflict_returns_404(self, client):
        response = client.patch(
            "/api/conflicts/nonexistent-id/review",
            json={"review_status": "REVIEWED"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# C. Patient-detail endpoint robustness tests
# ---------------------------------------------------------------------------

class TestPatientDetailEndpoints:
    """Patient API endpoints must handle zero entities and multiple documents correctly."""

    def test_patient_with_zero_entities_returns_valid_response(self, client, patient_id):
        """A patient with documents but no analysis run must return 200 on all endpoints."""
        from backend import repository
        from backend.db import init_db

        init_db()
        repository.ensure_patient(patient_id, display_name="Test Patient Zero Entities")

        # Patient endpoint
        resp = client.get(f"/api/patient/{patient_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == patient_id

        # Entities endpoint (zero entities)
        resp = client.get(f"/api/patient/{patient_id}/entities")
        assert resp.status_code == 200
        assert resp.json() == []

        # Timeline endpoint (zero events)
        resp = client.get(f"/api/patient/{patient_id}/timeline")
        assert resp.status_code == 200
        assert resp.json() == []

        # Conflicts endpoint (zero conflicts)
        resp = client.get(f"/api/patient/{patient_id}/conflicts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_patient_with_multiple_documents(self, client, patient_id):
        """Multiple documents for the same patient must all appear in the documents list."""
        from backend import repository
        from backend.db import init_db

        init_db()
        repository.ensure_patient(patient_id, display_name="Multi-Doc Patient")

        # Save two separate documents
        doc1_id = f"doc_{uuid.uuid4().hex[:8]}"
        doc2_id = f"doc_{uuid.uuid4().hex[:8]}"

        import hashlib
        for doc_id, filename in [(doc1_id, "clinic_note.pdf"), (doc2_id, "lab_report.pdf")]:
            repository.create_document(
                patient_id=patient_id,
                filename=filename,
                content_hash=hashlib.sha256(doc_id.encode()).hexdigest(),
                storage_path=None,
                data_origin="USER_UPLOAD",
            )

        resp = client.get(f"/api/patient/{patient_id}/documents")
        assert resp.status_code == 200
        docs = resp.json()
        assert len(docs) == 2
        filenames = {d["filename"] for d in docs}
        assert "clinic_note.pdf" in filenames
        assert "lab_report.pdf" in filenames

    def test_unknown_patient_returns_404(self, client):
        resp = client.get("/api/patient/nonexistent-patient-xyz")
        assert resp.status_code == 404

    def test_timeline_and_conflicts_for_unknown_patient_return_404(self, client):
        resp_t = client.get("/api/patient/nonexistent-patient-xyz/timeline")
        resp_c = client.get("/api/patient/nonexistent-patient-xyz/conflicts")
        assert resp_t.status_code == 404
        assert resp_c.status_code == 404

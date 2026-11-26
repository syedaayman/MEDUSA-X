"""Dataset adapter tests: normalisation, provenance labels and honest failure."""

from __future__ import annotations

import json

import pytest

from backend.datasets.base_adapter import DatasetUnavailable
from backend.datasets.dataset_registry import ADAPTERS, describe_adapters
from backend.datasets.synthea_adapter import SyntheaAdapter

FHIR_BUNDLE = {
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [
        {
            "resource": {
                "resourceType": "Patient",
                "id": "synthetic-0001",
                "name": [{"given": ["Ada"], "family": "Synthetic"}],
                "gender": "female",
                "birthDate": "1971-04-02",
            }
        },
        {
            "resource": {
                "resourceType": "Condition",
                "id": "condition-1",
                "subject": {"reference": "Patient/synthetic-0001"},
                "code": {"text": "Type 2 diabetes mellitus"},
                "onsetDateTime": "2022-05-01",
            }
        },
        {
            "resource": {
                "resourceType": "MedicationRequest",
                "id": "medication-1",
                "subject": {"reference": "Patient/synthetic-0001"},
                "medicationCodeableConcept": {"text": "Metformin 500 mg tablet"},
                "authoredOn": "2022-05-02",
                "dosageInstruction": [{"text": "500 mg twice daily"}],
            }
        },
        {
            "resource": {
                "resourceType": "AllergyIntolerance",
                "id": "allergy-1",
                "patient": {"reference": "Patient/synthetic-0001"},
                "code": {"text": "Penicillin"},
                "recordedDate": "2019-11-11",
            }
        },
        {
            "resource": {
                "resourceType": "Encounter",
                "id": "encounter-1",
                "subject": {"reference": "Patient/synthetic-0001"},
                "period": {"start": "2022-05-01T09:00:00Z"},
            }
        },
    ],
}


def test_registry_exposes_the_selected_datasets():
    names = set(ADAPTERS)
    assert {
        "synthea",
        "ekacare_medical_records_parsing",
        "ekacare_clinical_note_generation",
        "ekacare_medical_history_summarisation",
    } <= names

    described = {entry["name"]: entry for entry in describe_adapters()}
    assert described["synthea"]["data_origin"] == "SYNTHETIC_DATASET"
    for name in ("ekacare_medical_records_parsing", "ekacare_clinical_note_generation", "ekacare_medical_history_summarisation"):
        assert described[name]["data_origin"] == "EKACARE_EVALUATION"


def test_synthea_fhir_bundle_normalises_into_common_schema(tmp_path):
    root = tmp_path / "synthea"
    root.mkdir()
    (root / "bundle.json").write_text(json.dumps(FHIR_BUNDLE), encoding="utf-8")

    adapter = SyntheaAdapter(root=root)
    inspection = adapter.inspect_dataset()
    assert inspection["available"] is True
    assert inspection["file_count"] == 1

    records = adapter.load_records()
    assert records, "a Synthea FHIR bundle must produce records"

    entities = [entity for record in records for entity in record.entities]
    assert entities, "Synthea resources must map onto clinical entities"
    assert {entity["data_origin"] for entity in entities} == {"SYNTHETIC_DATASET"}
    assert all(str(entity.get("patient_id", "")).startswith("synthea:") for entity in entities)

    categories = {entity["category"] for entity in entities}
    assert "DIAGNOSIS" in categories
    assert "MEDICATION" in categories

    for entity in entities:
        assert entity.get("original_value") or entity.get("normalized_value")
        assert entity.get("source_record_id")


def test_missing_dataset_files_are_reported_not_faked(tmp_path):
    for name in (
        "ekacare_medical_records_parsing",
        "ekacare_clinical_note_generation",
        "ekacare_medical_history_summarisation",
    ):
        adapter = ADAPTERS[name](root=tmp_path / name)
        inspection = adapter.inspect_dataset()
        assert inspection["available"] is False
        assert inspection["file_count"] == 0
        assert inspection["note"], "an unavailable dataset must explain what is missing"

        try:
            records = adapter.load_records(limit=1)
        except DatasetUnavailable:
            records = []
        assert records == [], f"{name} must not invent records when no files are present"


def test_dataset_import_endpoints_report_status_without_crashing(client):
    listing = client.get("/api/datasets")
    assert listing.status_code == 200, listing.text

    status = client.get("/api/datasets/synthea/status")
    assert status.status_code == 200, status.text

    unknown = client.get("/api/datasets/not_a_dataset/status")
    assert 400 <= unknown.status_code < 500, "unknown datasets must be rejected"

    imported = client.post("/api/datasets/synthea/import")
    assert imported.status_code < 500, imported.text

"""Synthea adapter: synthetic longitudinal patient records.

Supports FHIR R4 bundles (JSON) and the CSV export. Synthea records never pass
through the PDF pipeline: they are structured data, so they are mapped directly
onto the common clinical schema and kept in the dataset namespace.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.datasets.base_adapter import BaseDatasetAdapter, NormalisedRecord
from backend.db import new_id

# Synthea CSV export file -> clinical category
CSV_CATEGORY = {
    "conditions": "DIAGNOSIS",
    "medications": "MEDICATION",
    "allergies": "ALLERGY",
    "observations": "LAB_RESULT",
    "procedures": "PROCEDURE",
    "immunizations": "PROCEDURE",
    "careplans": "PROCEDURE",
}

FHIR_CATEGORY = {
    "Condition": "DIAGNOSIS",
    "MedicationRequest": "MEDICATION",
    "MedicationStatement": "MEDICATION",
    "MedicationAdministration": "MEDICATION",
    "AllergyIntolerance": "ALLERGY",
    "Observation": "LAB_RESULT",
    "Procedure": "PROCEDURE",
    "Immunization": "PROCEDURE",
    "Encounter": "ENCOUNTER",
    "CarePlan": "PROCEDURE",
}


def _date_only(value: str | None) -> tuple[str | None, str]:
    """Return an ISO date and its precision without inventing missing parts."""
    if not value:
        return None, "UNKNOWN"
    text = str(value).strip()
    for fmt, precision in (("%Y-%m-%dT%H:%M:%S%z", "SECOND"), ("%Y-%m-%dT%H:%M:%SZ", "SECOND"), ("%Y-%m-%d", "DAY")):
        try:
            parsed = datetime.strptime(text[:19] if "T" in text else text, fmt if "T" not in text else "%Y-%m-%dT%H:%M:%S")
            return parsed.date().isoformat(), precision if "T" in text else "DAY"
        except ValueError:
            continue
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10], "DAY"
    return None, "UNKNOWN"


class SyntheaAdapter(BaseDatasetAdapter):
    name = "synthea"
    dataset_type = "SYNTHEA_SYNTHETIC_PATIENTS"
    source_url = "https://github.com/synthetichealth/synthea"
    licence = "Apache-2.0 (Synthea); data is synthetic, not real patients"
    patient_prefix = "synthea:"
    data_origin = "SYNTHETIC_DATASET"

    def load_records(self, limit: int | None = None) -> list[NormalisedRecord]:
        records: list[NormalisedRecord] = []
        for path in sorted(self.root.rglob("*.json")):
            records.extend(self._load_fhir(path))
        if not records:
            records = self._load_csv_directory()
        if limit:
            records = records[:limit]
        return [self.normalise_record(record) for record in records]

    # ------------------------------------------------------------------ FHIR
    def _load_fhir(self, path: Path) -> list[NormalisedRecord]:
        try:
            payload = self._read_json(path)
        except (json.JSONDecodeError, OSError):
            return []
        bundles = payload if isinstance(payload, list) else [payload]
        per_patient: dict[str, dict[str, Any]] = {}
        for bundle in bundles:
            entries = bundle.get("entry") if isinstance(bundle, dict) else None
            if not entries:
                continue
            for entry in entries:
                resource = (entry or {}).get("resource") or {}
                kind = resource.get("resourceType")
                patient_ref = self._patient_ref(resource)
                if kind == "Patient":
                    source_id = resource.get("id") or patient_ref
                    per_patient.setdefault(source_id, {"entities": [], "demographics": self._demographics(resource)})
                    continue
                if not patient_ref:
                    continue
                bucket = per_patient.setdefault(patient_ref, {"entities": [], "demographics": {}})
                entity = self._fhir_entity(resource, kind, patient_ref)
                if entity:
                    bucket["entities"].append(entity)

        records: list[NormalisedRecord] = []
        for source_id, bucket in per_patient.items():
            if not bucket["entities"] and not bucket["demographics"]:
                continue
            records.append(
                NormalisedRecord(
                    source_record_id=str(source_id),
                    record_type="PATIENT_BUNDLE",
                    original_format="FHIR_JSON",
                    original_location=str(path.relative_to(self.root)),
                    synthetic_patient_id=self.dataset_patient_id(str(source_id)),
                    entities=bucket["entities"],
                    metadata={"demographics": bucket["demographics"], "source_format": "FHIR"},
                )
            )
        return records

    @staticmethod
    def _patient_ref(resource: dict) -> str | None:
        for key in ("subject", "patient", "beneficiary"):
            reference = resource.get(key)
            if isinstance(reference, dict) and reference.get("reference"):
                return str(reference["reference"]).split("/")[-1]
        if resource.get("resourceType") == "Patient":
            return resource.get("id")
        return None

    @staticmethod
    def _demographics(resource: dict) -> dict:
        name = ""
        names = resource.get("name") or []
        if names and isinstance(names[0], dict):
            given = " ".join(names[0].get("given") or [])
            name = f"{given} {names[0].get('family', '')}".strip()
        return {
            "display_name": name or "Synthetic patient",
            "gender": resource.get("gender"),
            "birth_date": resource.get("birthDate"),
        }

    def _fhir_entity(self, resource: dict, kind: str, patient_ref: str) -> dict | None:
        category = FHIR_CATEGORY.get(kind)
        if not category:
            return None
        codeable = resource.get("code") or resource.get("medicationCodeableConcept") or {}
        text = codeable.get("text") if isinstance(codeable, dict) else None
        coding = (codeable.get("coding") or [{}])[0] if isinstance(codeable, dict) else {}
        label = text or coding.get("display") or coding.get("code")
        date_value = (
            resource.get("onsetDateTime")
            or resource.get("effectiveDateTime")
            or resource.get("authoredOn")
            or resource.get("performedPeriod", {}).get("start")
            or resource.get("occurrenceDateTime")
            or resource.get("period", {}).get("start")
            or resource.get("recordedDate")
        )
        clinical_date, precision = _date_only(date_value)
        if not label:
            return None
        attributes: dict[str, Any] = {}
        if kind in ("MedicationRequest", "MedicationStatement", "MedicationAdministration"):
            dosage = (resource.get("dosageInstruction") or resource.get("dosage") or [{}])[0]
            attributes = {
                "dosage": (dosage.get("text") if isinstance(dosage, dict) else None),
                "status": resource.get("status"),
                "route": ((dosage.get("route") or {}).get("text") if isinstance(dosage, dict) else None),
            }
        if kind == "Observation":
            quantity = resource.get("valueQuantity") or {}
            attributes = {
                "value": quantity.get("value") if isinstance(quantity, dict) else None,
                "unit": quantity.get("unit") if isinstance(quantity, dict) else None,
                "status": resource.get("status"),
            }
        if kind == "AllergyIntolerance":
            reaction = (resource.get("reaction") or [{}])[0]
            attributes = {
                "reaction": ((reaction.get("manifestation") or [{}])[0].get("text") if isinstance(reaction, dict) else None),
                "criticality": resource.get("criticality"),
                "clinical_status": (resource.get("clinicalStatus") or {}).get("coding", [{}])[0].get("code"),
            }
        if kind == "Condition":
            attributes = {"clinical_status": (resource.get("clinicalStatus") or {}).get("coding", [{}])[0].get("code")}
        return {
            "id": new_id("ent"),
            "patient_id": self.dataset_patient_id(patient_ref),
            "category": category,
            "original_value": str(label),
            "normalized_value": str(label).strip().lower(),
            "clinical_date": clinical_date,
            "date_precision": precision,
            "source_type": "FHIR",
            "source_document_id": None,
            "source_record_id": resource.get("id"),
            "source_page": None,
            "evidence_snippet": f"{kind}/{resource.get('id')}: {label}",
            "confidence": 1.0,
            "verification_status": "SOURCE_RECORD",
            "data_origin": self.data_origin,
            "attributes": attributes,
        }

    # ------------------------------------------------------------------- CSV
    def _load_csv_directory(self) -> list[NormalisedRecord]:
        per_patient: dict[str, list[dict]] = {}
        demographics: dict[str, dict] = {}
        patients_file = self.root / "patients.csv"
        if patients_file.exists():
            with patients_file.open(newline="", encoding="utf-8", errors="replace") as handle:
                for row in csv.DictReader(handle):
                    source_id = row.get("Id") or row.get("ID") or row.get("id")
                    if not source_id:
                        continue
                    demographics[source_id] = {
                        "display_name": f"{row.get('FIRST', '')} {row.get('LAST', '')}".strip() or "Synthetic patient",
                        "gender": row.get("GENDER"),
                        "birth_date": row.get("BIRTHDATE"),
                    }

        for path in sorted(self.root.glob("*.csv")):
            stem = path.stem.lower()
            category = CSV_CATEGORY.get(stem)
            if not category:
                continue
            with path.open(newline="", encoding="utf-8", errors="replace") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    patient_id = row.get("PATIENT") or row.get("patient")
                    if not patient_id:
                        continue
                    label = (
                        row.get("DESCRIPTION")
                        or row.get("DESCRIPTION")
                        or row.get("CODE")
                        or row.get("REASONCODE")
                        or row.get("VACCINE_CODE")
                    )
                    if not label:
                        continue
                    clinical_date, precision = _date_only(
                        row.get("START") or row.get("DATE") or row.get("OBSERVATIONDATE") or row.get("ENCOUNTERCLASS")
                    )
                    attributes = {
                        key.lower(): value
                        for key, value in row.items()
                        if key
                        and key.upper()
                        in {
                            "VALUE",
                            "UNITS",
                            "DOSE",
                            "DOSE_UNITS",
                            "ROUTE",
                            "FREQUENCY",
                            "STOP",
                            "REACTION1",
                            "DESCRIPTION",
                            "CODE",
                            "REASONCODE",
                            "STATUS",
                            "ENCOUNTERCLASS",
                        }
                    }
                    per_patient.setdefault(patient_id, []).append(
                        {
                            "id": new_id("ent"),
                            "patient_id": self.dataset_patient_id(patient_id),
                            "category": category,
                            "original_value": str(label),
                            "normalized_value": str(label).strip().lower(),
                            "clinical_date": clinical_date,
                            "date_precision": precision,
                            "source_type": "CSV",
                            "source_document_id": None,
                            "source_record_id": row.get("Id") or row.get("ID"),
                            "source_page": None,
                            "evidence_snippet": f"{path.name}: {str(label)[:160]}",
                            "confidence": 1.0,
                            "verification_status": "SOURCE_RECORD",
                            "data_origin": self.data_origin,
                            "attributes": attributes,
                        }
                    )

        return [
            NormalisedRecord(
                source_record_id=str(source_id),
                record_type="PATIENT_BUNDLE",
                original_format="CSV",
                original_location="*.csv",
                synthetic_patient_id=self.dataset_patient_id(str(source_id)),
                entities=entities,
                metadata={"demographics": demographics.get(source_id, {}), "source_format": "CSV"},
            )
            for source_id, entities in per_patient.items()
        ]

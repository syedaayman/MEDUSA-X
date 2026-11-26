"""Synthetic sample-case endpoints for safe, repeatable demonstrations.

These endpoints build small in-memory PDFs from clearly labelled synthetic
text, run them through the normal ingestion + analysis pipeline, and return a
fresh patient id. They never touch the production document store beyond the
normal upload path and never fabricate a processing result.
"""

from __future__ import annotations

import uuid
from typing import Any

import fitz
from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend import repository
from backend.agents import orchestrator
from backend.ingestion.pipeline import ingest_document

router = APIRouter(tags=["samples"])

SCENARIOS: dict[str, list[tuple[str, list[str]]]] = {
    "medication-discrepancy": [
        (
            "discharge.pdf",
            [
                "Discharge Summary",
                "Patient: Synthetic Demo Patient",
                "Date: 2024-03-01",
                "Diagnosis: Type 2 diabetes mellitus",
                "Medications:",
                "- Metformin 500 mg twice daily",
                "Allergy: Penicillin",
                "Vitals: Blood pressure 138/86 mmHg",
                "Laboratory:",
                "HbA1c 8.4",
                "Fasting glucose 168 mg/dL",
                "Creatinine 0.9 mg/dL",
            ],
        ),
        (
            "prescription.pdf",
            [
                "Prescription",
                "Patient: Synthetic Demo Patient",
                "Date: 2024-03-01",
                "Medications:",
                "- Metformin 1000 mg twice daily",
            ],
        ),
    ],
    "missing-lab": [
        (
            "consult.pdf",
            [
                "Consultation Note",
                "Patient: Synthetic Demo Patient",
                "Date: 2024-04-10",
                "Diagnosis: Hypertension",
                "Medications:",
                "- Amlodipine 5 mg once daily",
                "Laboratory:",
                "HbA1c 7.2",
                "Creatinine 1.1 mg/dL",
            ],
        ),
        (
            "lab.pdf",
            [
                "Laboratory Report",
                "Patient: Synthetic Demo Patient",
                "Date: 2024-04-10",
                "Laboratory:",
                "Total cholesterol 224 mg/dL",
                "LDL cholesterol 148 mg/dL",
            ],
        ),
    ],
    "multi-visit-timeline": [
        (
            "jan.pdf",
            [
                "Consultation Note",
                "Patient: Synthetic Demo Patient",
                "Date: 2024-01-10",
                "Diagnosis: Type 2 diabetes mellitus",
                "Medications:",
                "- Metformin 500 mg twice daily",
                "Laboratory:",
                "HbA1c 8.4",
            ],
        ),
        (
            "jun.pdf",
            [
                "Discharge Summary",
                "Patient: Synthetic Demo Patient",
                "Date: 2024-06-20",
                "Diagnosis: Hypertension",
                "Medications:",
                "- Metformin 1000 mg twice daily",
                "- Atorvastatin 10 mg at night",
                "Laboratory:",
                "HbA1c 7.8",
                "Creatinine 0.9 mg/dL",
                "Vitals: Blood pressure 132/84 mmHg",
            ],
        ),
        (
            "lab.pdf",
            [
                "Laboratory Report",
                "Patient: Synthetic Demo Patient",
                "Date: 2024-06-20",
                "Laboratory:",
                "Total cholesterol 190 mg/dL",
                "LDL cholesterol 112 mg/dL",
            ],
        ),
    ],
    "DEMO-001": [
        (
            "consultation_jan2024.pdf",
            [
                "Consultation Note",
                "Patient: Synthetic Demo Patient 1",
                "Date: 2024-01-15",
                "Diagnosis: Type 2 diabetes mellitus",
                "Diagnosis: Essential hypertension",
                "Diagnosis: Dyslipidemia",
                "Symptoms: increased thirst, frequent urination, fatigue, occasional headache",
                "Medications:",
                "- Metformin 500 mg twice daily",
                "- Amlodipine 5 mg once daily",
                "Allergy: Penicillin",
                "Vitals: Blood pressure 142/90 mmHg",
                "Vitals: Pulse 82 bpm",
                "Vitals: Weight 82 kg",
                "Laboratory:",
                "HbA1c 8.4",
                "Fasting glucose 168 mg/dL",
                "Total cholesterol 224 mg/dL",
                "LDL cholesterol 148 mg/dL",
                "Creatinine 0.9 mg/dL",
            ],
        ),
        (
            "lab_jun2024.pdf",
            [
                "Laboratory Report",
                "Patient: Synthetic Demo Patient 1",
                "Date: 2024-06-20",
                "Laboratory:",
                "HbA1c 7.8",
                "Fasting glucose 145 mg/dL",
                "Total cholesterol 190 mg/dL",
                "LDL cholesterol 112 mg/dL",
                "Creatinine 0.9 mg/dL",
            ],
        ),
        (
            "prescription_sep2024.pdf",
            [
                "Prescription",
                "Patient: Synthetic Demo Patient 1",
                "Date: 2024-09-10",
                "Medications:",
                "- Metformin 1000 mg twice daily",
                "- Atorvastatin 10 mg at night",
                "- Amlodipine 5 mg once daily",
                "Allergy: NKDA",
            ],
        ),
        (
            "followup_nov2024.pdf",
            [
                "Discharge Summary",
                "Patient: Synthetic Demo Patient 1",
                "Date: 2024-11-05",
                "Diagnosis: Type 2 diabetes mellitus",
                "Diagnosis: Essential hypertension",
                "Medications:",
                "- Metformin 500 mg twice daily",
                "- Atorvastatin 20 mg at night",
                "- Amlodipine 5 mg once daily",
                "Laboratory:",
                "HbA1c 7.2",
                "Vitals: Blood pressure 128/80 mmHg",
                "Vitals: Pulse 76 bpm",
                "Vitals: Weight 79 kg",
            ],
        ),
    ],
    "DEMO-002": [
        (
            "consultation_feb2024.pdf",
            [
                "Consultation Note",
                "Patient: Synthetic Demo Patient 2",
                "Date: 2024-02-12",
                "Diagnosis: Coronary artery disease",
                "Diagnosis: Hypertension",
                "Diagnosis: Hyperlipidemia",
                "Symptoms: intermittent chest discomfort, exertional breathlessness, fatigue",
                "Medications:",
                "- Aspirin 75 mg once daily",
                "- Clopidogrel 75 mg once daily",
                "- Atorvastatin 40 mg at night",
                "- Metoprolol 25 mg twice daily",
                "Allergy: Penicillin",
                "Vitals: Blood pressure 148/92 mmHg",
                "Vitals: Pulse 88 bpm",
                "Laboratory:",
                "Total cholesterol 248 mg/dL",
                "LDL cholesterol 162 mg/dL",
                "Hemoglobin 13.8 g/dL",
                "Creatinine 1.0 mg/dL",
            ],
        ),
        (
            "angiography_mar2024.pdf",
            [
                "Diagnostic Report",
                "Patient: Synthetic Demo Patient 2",
                "Date: 2024-03-05",
                "Procedure: Coronary angiography",
                "Procedure: Coronary stent placement",
                "Laboratory:",
                "Creatinine 1.0 mg/dL",
            ],
        ),
        (
            "followup_jul2024.pdf",
            [
                "Follow-up Consultation",
                "Patient: Synthetic Demo Patient 2",
                "Date: 2024-07-18",
                "Diagnosis: Coronary artery disease",
                "Medications:",
                "- Aspirin 75 mg once daily",
                "- Clopidogrel 75 mg once daily",
                "- Atorvastatin 80 mg at night",
                "- Metoprolol 25 mg twice daily",
                "- Glibenclamide 5 mg once daily",
                "Allergy: NKDA",
                "Laboratory:",
                "Total cholesterol 178 mg/dL",
                "LDL cholesterol 96 mg/dL",
                "Hemoglobin 14.1 g/dL",
                "Creatinine 1.0 mg/dL",
                "Vitals: Blood pressure 126/78 mmHg",
            ],
        ),
        (
            "cardiology_sep2024.pdf",
            [
                "Specialist Assessment",
                "Patient: Synthetic Demo Patient 2",
                "Date: 2024-09-22",
                "Diagnosis: Coronary artery disease",
                "Diagnosis: Hypertension",
                "Medications:",
                "- Aspirin 75 mg once daily",
                "- Atorvastatin 40 mg at night",
                "- Metoprolol 25 mg twice daily",
                "Laboratory:",
                "LDL cholesterol 104 mg/dL",
                "Vitals: Blood pressure 124/76 mmHg",
            ],
        ),
    ],
    "DEMO-003": [
        (
            "consultation_mar2024.pdf",
            [
                "Consultation Note",
                "Patient: Synthetic Demo Patient 3",
                "Date: 2024-03-08",
                "Diagnosis: Bronchial asthma",
                "Diagnosis: Allergic rhinitis",
                "Symptoms: wheezing, intermittent cough, nasal congestion, fatigue",
                "Medications:",
                "- Budesonide/formoterol inhaler twice daily",
                "- Salbutamol inhaler as needed",
                "- Cetirizine 10 mg as needed",
                "Laboratory:",
                "TSH 6.8 mIU/L",
                "Free T4 0.9 ng/dL",
            ],
        ),
        (
            "thyroid_apr2024.pdf",
            [
                "Laboratory Report",
                "Patient: Synthetic Demo Patient 3",
                "Date: 2024-04-15",
                "Diagnosis: Hypothyroidism",
                "Medications:",
                "- Levothyroxine 50 mcg once daily",
                "Laboratory:",
                "TSH 6.8 mIU/L",
                "Free T4 0.9 ng/dL",
            ],
        ),
        (
            "followup_jul2024.pdf",
            [
                "Follow-up Consultation",
                "Patient: Synthetic Demo Patient 3",
                "Date: 2024-07-22",
                "Diagnosis: Bronchial asthma",
                "Diagnosis: Hypothyroidism",
                "Medications:",
                "- Budesonide/formoterol inhaler twice daily",
                "- Salbutamol inhaler as needed",
                "- Levothyroxine 75 mcg once daily",
                "- Cetirizine 10 mg as needed",
                "Laboratory:",
                "TSH 3.2 mIU/L",
                "Free T4 1.2 ng/dL",
                "Vitals: Blood pressure 118/74 mmHg",
            ],
        ),
        (
            "respiratory_sep2024.pdf",
            [
                "Specialist Assessment",
                "Patient: Synthetic Demo Patient 3",
                "Date: 2024-09-12",
                "Diagnosis: Bronchial asthma",
                "Medications:",
                "- Budesonide/formoterol inhaler twice daily",
                "- Salbutamol inhaler as needed",
                "- Levothyroxine 50 mcg once daily",
                "Laboratory:",
                "TSH 3.2 mIU/L",
            ],
        ),
    ],
}


def _make_pdf(lines: list[str]) -> bytes:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=10)
        y += 16
    blob = document.tobytes()
    document.close()
    return blob


def _execute_run(patient_id: str, run_id: str, document_ids: list[str]) -> None:
    try:
        orchestrator.run_analysis(patient_id, document_ids=document_ids, run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        repository.update_run(run_id, status="FAILED", current_agent=None, error_message=f"{type(exc).__name__}: {exc}")


@router.post("/api/samples/{scenario}/load")
def load_sample(scenario: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Unknown sample scenario: {scenario}")
    patient_id = scenario if scenario.startswith("DEMO-") else f"sample-{scenario}-{uuid.uuid4().hex[:8]}"
    repository.ensure_patient(patient_id, display_name=f"Synthetic Demo: {scenario}")
    document_ids: list[str] = []
    for filename, lines in SCENARIOS[scenario]:
        result = ingest_document(patient_id, filename, _make_pdf(lines))
        document_ids.append(result["document"]["id"])
    run = repository.create_run(patient_id, document_ids, "agents_sdk+deterministic")
    background_tasks.add_task(_execute_run, patient_id, run["id"], document_ids)
    return {
        "patient_id": patient_id,
        "scenario": scenario,
        "documents": len(document_ids),
        "analysis_run_id": run["id"],
        "status": "QUEUED",
        "synthetic": True,
    }

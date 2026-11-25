"""Upload and analysis-run API routes."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from backend import repository
from backend.agents import orchestrator
from backend.ingestion.pipeline import IngestionError, ingest_document
from backend.schemas import AnalysisRun, AgentActivity, UploadedDocument

router = APIRouter(tags=["upload"])

_RUNNING: set[str] = set()
_RUN_LOCK = threading.Lock()


def _execute_run(patient_id: str, run_id: str, document_ids: list[str]) -> None:
    """Background worker: never leaves a run stuck in RUNNING on failure."""
    try:
        orchestrator.run_analysis(patient_id, document_ids=document_ids, run_id=run_id)
    except Exception as exc:  # noqa: BLE001 - recorded for the operator
        repository.update_run(
            run_id,
            status="FAILED",
            current_agent=None,
            completed_at=repository.utc_now() if hasattr(repository, "utc_now") else None,
            error_message=f"{type(exc).__name__}: {exc}",
        )
        repository.add_activity(
            run_id,
            "ORCHESTRATOR",
            "Workflow aborted with an unhandled error.",
            status="FAILED",
            detail={"error": f"{type(exc).__name__}: {exc}"},
        )
    finally:
        with _RUN_LOCK:
            _RUNNING.discard(run_id)


def _start_run(patient_id: str, document_ids: list[str]) -> dict:
    run = repository.create_run(patient_id, document_ids, "agents_sdk+deterministic")
    with _RUN_LOCK:
        _RUNNING.add(run["id"])
    return run


@router.post("/api/upload", response_model=dict)
async def upload_documents(
    background_tasks: BackgroundTasks,
    patient_id: str = Form(...),
    display_name: str | None = Form(default=None),
    start_analysis: bool = Form(default=True),
    reprocess: bool = Form(default=False),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """Accept one or more PDFs, extract them and optionally start the analysis run."""
    if not patient_id.strip():
        raise HTTPException(status_code=422, detail="patient_id is required")
    if not files:
        raise HTTPException(status_code=422, detail="At least one PDF file is required")

    repository.ensure_patient(patient_id.strip(), display_name)
    uploaded: list[dict] = []
    errors: list[dict] = []
    document_ids: list[str] = []

    for upload in files:
        content = await upload.read()
        try:
            result = ingest_document(
                patient_id.strip(),
                upload.filename or "document.pdf",
                content,
                reprocess=reprocess,
            )
        except IngestionError as exc:
            errors.append({"filename": upload.filename, "error": str(exc)})
            continue
        document = result["document"]
        document_ids.append(document["id"])
        uploaded.append(
            {
                **UploadedDocument.model_validate(document).model_dump(mode="json"),
                "duplicate": result["duplicate"],
                "extraction": result["extraction"],
            }
        )

    if not uploaded and errors:
        raise HTTPException(status_code=400, detail={"errors": errors, "uploaded": []})

    run = None
    if start_analysis and document_ids:
        run = _start_run(patient_id.strip(), document_ids)
        background_tasks.add_task(_execute_run, patient_id.strip(), run["id"], document_ids)

    return {
        "patient_id": patient_id.strip(),
        "documents": uploaded,
        "errors": errors,
        "analysis_run_id": run["id"] if run else None,
        "status": "QUEUED" if run else "UPLOADED",
    }


@router.post("/api/patient/{patient_id}/process", response_model=dict)
def process_patient(
    patient_id: str,
    background_tasks: BackgroundTasks,
    document_ids: str | None = None,
    focus: str = "",
) -> dict[str, Any]:
    """Start a new analysis run over the patient's stored documents."""
    patient = repository.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    documents = repository.list_documents(patient_id)
    if not documents:
        raise HTTPException(status_code=400, detail="Patient has no documents to analyse")

    selected = [item for item in (document_ids or "").split(",") if item.strip()]
    if selected:
        known = {doc["id"] for doc in documents}
        unknown = [item for item in selected if item not in known]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown document ids for this patient: {unknown}")

    run = _start_run(patient_id, selected or [doc["id"] for doc in documents])
    background_tasks.add_task(_execute_run, patient_id, run["id"], selected)
    return {"analysis_run_id": run["id"], "status": "QUEUED", "documents": len(selected or documents)}


@router.get("/api/analysis/{run_id}", response_model=AnalysisRun)
def get_analysis(run_id: str) -> AnalysisRun:
    run = repository.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Analysis run {run_id} not found")
    return AnalysisRun.model_validate(run)


@router.get("/api/analysis/{run_id}/activity", response_model=list[AgentActivity])
def get_analysis_activity(run_id: str) -> list[AgentActivity]:
    if not repository.get_run(run_id):
        raise HTTPException(status_code=404, detail=f"Analysis run {run_id} not found")
    return [AgentActivity.model_validate(item) for item in repository.list_activity(run_id)]


@router.get("/api/patient/{patient_id}/analysis", response_model=list[AnalysisRun])
def list_patient_analysis(patient_id: str) -> list[AnalysisRun]:
    return [AnalysisRun.model_validate(run) for run in repository.list_runs(patient_id)]

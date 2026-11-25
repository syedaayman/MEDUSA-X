"""Dataset management API routes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from backend import repository
from backend.datasets import dataset_service
from backend.datasets.dataset_registry import describe_adapters

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("")
def list_datasets() -> dict:
    """List registered adapters with their real local availability."""
    dataset_service.sync_dataset_sources()
    sources = repository.list_dataset_sources()
    counts = {source["id"]: repository.count_dataset_records(source["id"]) for source in sources}
    adapters = {adapter["name"]: adapter for adapter in describe_adapters()}
    merged = []
    for source in sources:
        adapter = adapters.get(source["name"], {})
        merged.append(
            {
                **source,
                "available": adapter.get("available", False),
                "file_count": adapter.get("file_count", 0),
                "formats": adapter.get("formats", []),
                "record_counts": counts.get(source["id"], {}),
                "records_imported": sum(counts.get(source["id"], {}).values()),
                "data_origin": adapter.get("data_origin"),
            }
        )
    return {"datasets": merged}


@router.get("/{dataset_name}/status")
def dataset_status(dataset_name: str) -> dict:
    try:
        return dataset_service.dataset_status(dataset_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{dataset_name}/import")
def import_dataset(
    dataset_name: str,
    limit: int = Query(default=25, ge=1, le=500),
) -> dict:
    """Import a bounded sample. Never runs automatically at startup."""
    try:
        return dataset_service.import_dataset(dataset_name, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{dataset_name}/evaluate")
def evaluate_dataset(
    dataset_name: str,
    evaluation_type: str = Query(default="EXTRACTION", pattern="^(EXTRACTION|SUMMARY)$"),
    limit: int = Query(default=20, ge=1, le=200),
) -> dict:
    try:
        if evaluation_type == "SUMMARY":
            return dataset_service.evaluate_summary(dataset_name, limit=limit)
        return dataset_service.evaluate_extraction(dataset_name, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{dataset_name}/evaluation")
def evaluation_report(dataset_name: str) -> dict:
    try:
        return dataset_service.evaluation_report(dataset_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{dataset_name}/patients/{dataset_patient_id}")
def dataset_patient(dataset_name: str, dataset_patient_id: str) -> dict:
    """Read dataset context only; dataset patients never enter uploaded records."""
    try:
        return dataset_service.dataset_patient_context(dataset_name, dataset_patient_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

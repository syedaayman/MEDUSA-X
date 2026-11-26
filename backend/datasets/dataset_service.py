"""Dataset import and evaluation services.

Imports and evaluations run only when explicitly triggered, are recorded with
their real counts, and never mix dataset records into uploaded patient data.
"""

from __future__ import annotations

import re
from typing import Any

from backend import repository
from backend.datasets.dataset_registry import ADAPTERS, get_adapter
from backend.schemas import EvaluationMetrics

_TOKEN = re.compile(r"[a-z0-9]{3,}")


def _tokens(text: str | None) -> set[str]:
    return set(_TOKEN.findall((text or "").lower()))


def sync_dataset_sources() -> list[dict]:
    """Register each adapter once; no files are read here."""
    for name, adapter_cls in ADAPTERS.items():
        adapter = adapter_cls()
        repository.upsert_dataset_source(
            name=name,
            title=adapter.title,
            source_url=adapter.source_url,
            version="local",
            licence=adapter.licence,
            dataset_type=adapter.dataset_type,
            description=adapter.description,
        )
    return repository.list_dataset_sources()


def dataset_status(name: str) -> dict:
    source = repository.get_dataset_source(name)
    if not source:
        raise KeyError(f"Unknown dataset '{name}'")
    adapter = get_adapter(name)
    inspection = adapter.inspect_dataset()
    counts = repository.count_dataset_records(source["id"])
    evaluations = repository.list_evaluations(source["id"], limit=20)
    return {
        "dataset": source,
        "inspection": inspection,
        "record_counts": counts,
        "import_runs": repository.get_import_runs(source["id"]),
        "evaluations": evaluations,
        "records_imported": sum(counts.values()),
    }


def import_dataset(name: str, limit: int = 25) -> dict:
    """Import a bounded sample and record exactly what happened."""
    source = repository.get_dataset_source(name) or (sync_dataset_sources() and repository.get_dataset_source(name))
    if not source:
        raise KeyError(f"Unknown dataset '{name}'")
    adapter = get_adapter(name)
    inspection = adapter.inspect_dataset()
    run_id = repository.start_import_run(source["id"])
    if not inspection.get("available"):
        message = [inspection["note"]] if inspection.get("note") else ["Dataset files are not present locally."]
        repository.finish_import_run(run_id, source["id"], "UNAVAILABLE", 0, 0, list(message))
        return {
            "dataset": name,
            "status": "UNAVAILABLE",
            "records_processed": 0,
            "records_failed": 0,
            "errors": list(message),
            "inspection": inspection,
        }

    processed = 0
    failed = 0
    errors: list[str] = []
    try:
        records = adapter.load_records(limit=limit)
    except Exception as exc:  # noqa: BLE001 - adapter failure must not break the app
        repository.finish_import_run(run_id, source["id"], "FAILED", 0, 0, [f"{type(exc).__name__}: {exc}"])
        return {
            "dataset": name,
            "status": "FAILED",
            "records_processed": 0,
            "records_failed": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "inspection": inspection,
        }

    for record in records:
        problems = adapter.validate_record(record)
        if problems:
            failed += 1
            errors.append(f"{record.source_record_id}: {'; '.join(problems)}")
            continue
        try:
            repository.save_dataset_record(
                source["id"],
                record.source_record_id,
                record.record_type,
                record.synthetic_patient_id,
                record.original_format,
                record.original_location,
                record.data_origin,
                record.metadata,
                {"entities": record.entities, "reference_output": record.reference_output},
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append(f"{record.source_record_id}: {type(exc).__name__}: {exc}")

    status = "COMPLETED" if processed and not failed else ("PARTIAL" if processed else "FAILED")
    repository.finish_import_run(run_id, source["id"], status, processed, failed, errors)
    repository.log_audit(None, "dataset_import_service", "DATASET_IMPORTED", {"dataset": name, "processed": processed, "failed": failed})
    return {
        "dataset": name,
        "status": status,
        "records_processed": processed,
        "records_failed": failed,
        "errors": errors[:20],
        "inspection": inspection,
    }


def _extraction_metrics(generated: list[str], reference: list[str]) -> EvaluationMetrics:
    generated_set = {value for value in generated if value}
    reference_set = {value for value in reference if value}
    if not generated_set and not reference_set:
        return EvaluationMetrics(samples=0, notes=["No comparable entities in this record."])
    true_positive = len(generated_set & reference_set)
    precision = true_positive / len(generated_set) if generated_set else 0.0
    recall = true_positive / len(reference_set) if reference_set else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return EvaluationMetrics(
        samples=len(reference_set),
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        missing_fields=len(reference_set - generated_set),
        unsupported_entities=len(generated_set - reference_set),
        notes=[],
    )


def evaluate_extraction(name: str, limit: int = 20) -> dict:
    """Compare deterministic extraction with whatever ground truth exists."""
    source = repository.get_dataset_source(name) or (sync_dataset_sources() and repository.get_dataset_source(name))
    if not source:
        raise KeyError(f"Unknown dataset '{name}'")
    records = repository.list_dataset_records(source["id"], limit=limit)
    evaluated = 0
    skipped = 0
    totals = {"tp": 0, "generated": 0, "reference": 0}
    for record in records:
        payload = record.get("payload") or {}
        reference_entities = payload.get("entities") or []
        reference_values = [entity.get("normalized_value") or entity.get("original_value") for entity in reference_entities]
        if not reference_values:
            skipped += 1
            continue
        generated_values = [
            entity.get("normalized_value") or entity.get("original_value")
            for entity in (payload.get("generated_entities") or [])
        ]
        metrics = _extraction_metrics(generated_values, reference_values)
        repository.save_evaluation(
            source["id"],
            record["id"],
            "Clinical Structuring Agent",
            "EXTRACTION",
            {"entities": generated_values[:50]},
            {"entities": reference_values[:50]},
            metrics.f1,
            metrics.model_dump(),
        )
        totals["tp"] += len(set(generated_values) & set(reference_values))
        totals["generated"] += len(set(generated_values))
        totals["reference"] += len(set(reference_values))
        evaluated += 1

    precision = totals["tp"] / totals["generated"] if totals["generated"] else 0.0
    recall = totals["tp"] / totals["reference"] if totals["reference"] else 0.0
    return {
        "dataset": name,
        "evaluation_type": "EXTRACTION",
        "records_evaluated": evaluated,
        "records_without_ground_truth": skipped,
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round((2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0, 4),
        },
        "notes": (
            ["No stored record contains generated entities, so no extraction comparison could be scored."]
            if not totals["generated"]
            else []
        ),
    }


def evaluate_summary(name: str, limit: int = 20) -> dict:
    """Compare stored generated summaries with reference summaries."""
    source = repository.get_dataset_source(name) or (sync_dataset_sources() and repository.get_dataset_source(name))
    if not source:
        raise KeyError(f"Unknown dataset '{name}'")
    records = repository.list_dataset_records(source["id"], limit=limit)
    scored = 0
    missing = 0
    retained_total = 0.0
    unsupported_total = 0
    for record in records:
        payload = record.get("payload") or {}
        reference = ((payload.get("reference_output") or {}).get("summary")) or ""
        generated = payload.get("generated_summary") or ""
        if not reference or not generated:
            missing += 1
            continue
        reference_tokens = _tokens(reference)
        generated_tokens = _tokens(generated)
        retained = len(reference_tokens & generated_tokens) / len(reference_tokens) if reference_tokens else 0.0
        unsupported = len(generated_tokens - reference_tokens)
        repository.save_evaluation(
            source["id"],
            record["id"],
            "Timeline and Summary Agent",
            "SUMMARY",
            {"summary": generated[:4000]},
            {"summary": reference[:4000]},
            round(retained, 4),
            {"facts_retained_ratio": round(retained, 4), "unsupported_terms": unsupported},
        )
        retained_total += retained
        unsupported_total += unsupported
        scored += 1
    return {
        "dataset": name,
        "evaluation_type": "SUMMARY",
        "records_evaluated": scored,
        "records_without_ground_truth": missing,
        "metrics": {
            "mean_fact_retention": round(retained_total / scored, 4) if scored else 0.0,
            "unsupported_terms": unsupported_total,
        },
        "notes": (
            ["No record contains both a generated and a reference summary, so no summary score was computed."]
            if not scored
            else ["Scores measure term overlap with the reference summary only; they are not a clinical accuracy claim."]
        ),
    }


def evaluation_report(name: str) -> dict:
    source = repository.get_dataset_source(name)
    if not source:
        raise KeyError(f"Unknown dataset '{name}'")
    return {
        "dataset": source,
        "evaluations": repository.list_evaluations(source["id"], limit=100),
    }


def dataset_patient_context(name: str, dataset_patient_id: str) -> dict:
    """Retrieve a dataset patient's stored entities without touching uploads."""
    source = repository.get_dataset_source(name)
    if not source:
        raise KeyError(f"Unknown dataset '{name}'")
    records = repository.list_dataset_records(source["id"], synthetic_patient_id=dataset_patient_id, limit=50)
    entities: list[dict] = []
    for record in records:
        entities.extend(((record.get("payload") or {}).get("entities") or []))
    return {
        "dataset": name,
        "dataset_patient_id": dataset_patient_id,
        "data_origin": source.get("dataset_type"),
        "records": len(records),
        "entities": entities,
        "counts": _category_counts(entities),
    }


def _category_counts(entities: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in entities:
        category = str(entity.get("category") or "UNKNOWN")
        counts[category] = counts.get(category, 0) + 1
    return counts

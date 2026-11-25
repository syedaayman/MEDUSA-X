"""EkaCare evaluation adapters.

These datasets are used for evaluation, never as real patient uploads. The
adapters read the local files that the operator placed under the dataset
directory, keep the upstream record identifiers, and expose whatever ground
truth the files actually contain. When a file has no annotation, the adapter
reports that instead of inventing a reference answer.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from backend.datasets.base_adapter import BaseDatasetAdapter, NormalisedRecord
from backend.db import new_id

TEXT_SUFFIXES = {".txt", ".md", ".text"}
JSON_SUFFIXES = {".json", ".jsonl"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".pdf"}


def _first_key(payload: dict, candidates: list[str]) -> Any:
    for key in candidates:
        if key in payload and payload[key] not in (None, "", []):
            return payload[key]
    return None


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(_flatten_text(item) for item in value).strip()
    if isinstance(value, dict):
        return "\n".join(f"{key}: {_flatten_text(item)}" for key, item in value.items()).strip()
    return ""


def _entities_from_structured(payload: Any, patient_id: str, origin: str) -> list[dict]:
    """Map a ground-truth/structured payload onto the common entity schema."""
    category_map = {
        "diagnosis": "DIAGNOSIS",
        "diagnoses": "DIAGNOSIS",
        "condition": "DIAGNOSIS",
        "conditions": "DIAGNOSIS",
        "symptom": "SYMPTOM",
        "symptoms": "SYMPTOM",
        "medication": "MEDICATION",
        "medications": "MEDICATION",
        "medicine": "MEDICATION",
        "medicines": "MEDICATION",
        "drug": "MEDICATION",
        "drugs": "MEDICATION",
        "allergy": "ALLERGY",
        "allergies": "ALLERGY",
        "investigation": "LAB_RESULT",
        "investigations": "LAB_RESULT",
        "lab": "LAB_RESULT",
        "labs": "LAB_RESULT",
        "laboratory": "LAB_RESULT",
        "test": "LAB_RESULT",
        "tests": "LAB_RESULT",
        "procedure": "PROCEDURE",
        "procedures": "PROCEDURE",
        "advice": "NOTE",
        "notes": "NOTE",
    }
    entities: list[dict] = []

    def walk(node: Any, hint: str | None = None) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                category = category_map.get(str(key).lower())
                if category:
                    for item in value if isinstance(value, list) else [value]:
                        text = _flatten_text(item)
                        if text:
                            entities.append(
                                {
                                    "id": new_id("ent"),
                                    "patient_id": patient_id,
                                    "category": category,
                                    "original_value": text[:400],
                                    "normalized_value": text.strip().lower()[:400],
                                    "clinical_date": None,
                                    "date_precision": "UNKNOWN",
                                    "source_type": "EKACARE",
                                    "source_document_id": None,
                                    "source_record_id": None,
                                    "source_page": None,
                                    "evidence_snippet": text[:400],
                                    "confidence": 1.0,
                                    "verification_status": "SOURCE_RECORD",
                                    "data_origin": origin,
                                    "attributes": {"ground_truth_key": key},
                                }
                            )
                else:
                    walk(value, str(key).lower())
        elif isinstance(node, list):
            for item in node:
                walk(item, hint)

    walk(payload)
    return entities


class _EkaCareBase(BaseDatasetAdapter):
    dataset_type = "EKACARE_EVALUATION"
    source_url = "https://huggingface.co/ekacare/datasets"
    licence = "See the dataset card on Hugging Face before use"
    patient_prefix = "eka:"
    data_origin = "EKACARE_EVALUATION"
    record_type = "EVALUATION_EXAMPLE"

    def _iter_json(self, path: Path) -> list[dict]:
        if path.suffix.lower() == ".jsonl":
            rows: list[dict] = []
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return rows
        try:
            payload = self._read_json(path)
        except (json.JSONDecodeError, OSError):
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("data", "records", "examples", "rows", "annotations"):
                if isinstance(payload.get(key), list):
                    return [item for item in payload[key] if isinstance(item, dict)]
            return [payload]
        return []

    def _iter_csv(self, path: Path) -> list[dict]:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            return [row for row in csv.DictReader(handle)]

    def _record_id(self, payload: dict, fallback: str) -> str:
        return str(_first_key(payload, ["id", "record_id", "uid", "image_id", "sample_id", "file_name", "name"]) or fallback)


class EkaCareParsingAdapter(_EkaCareBase):
    """Medical records parsing validation set: document images plus annotations."""

    name = "ekacare_medical_records_parsing"
    record_type = "PARSING_DOCUMENT"

    def load_records(self, limit: int | None = None) -> list[NormalisedRecord]:
        records: list[NormalisedRecord] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in JSON_SUFFIXES:
                for index, payload in enumerate(self._iter_json(path)):
                    records.append(self._parsing_record(payload, path, index))
            elif suffix in TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="replace")
                records.append(self._text_record(path.stem, text, path, "TEXT"))
            elif suffix in IMAGE_SUFFIXES:
                records.append(self._text_record(path.stem, "", path, "IMAGE"))
        if limit:
            records = records[:limit]
        return [self.normalise_record(record) for record in records]

    def _parsing_record(self, payload: dict, path: Path, index: int) -> NormalisedRecord:
        record_id = self._record_id(payload, f"{path.stem}-{index}")
        patient_id = self.dataset_patient_id(record_id)
        annotations = _first_key(payload, ["annotations", "ground_truth", "structured", "label", "labels", "output", "target"])
        entities = _entities_from_structured(annotations, patient_id, self.data_origin) if annotations else []
        return NormalisedRecord(
            source_record_id=record_id,
            record_type=self.record_type,
            original_format="JSON_ANNOTATION",
            original_location=str(path.relative_to(self.root)),
            synthetic_patient_id=patient_id,
            entities=entities,
            metadata={
                "document_kind": _first_key(payload, ["document_type", "doc_type", "type"]) or "UNKNOWN",
                "image_reference": _first_key(payload, ["image", "image_path", "file_name", "document"]),
                "has_ground_truth": bool(annotations),
            },
            reference_output={"annotations": annotations} if annotations else None,
        )

    def _text_record(self, record_id: str, text: str, path: Path, kind: str) -> NormalisedRecord:
        patient_id = self.dataset_patient_id(record_id)
        return NormalisedRecord(
            source_record_id=record_id,
            record_type=self.record_type,
            original_format=kind,
            original_location=str(path.relative_to(self.root)),
            synthetic_patient_id=patient_id,
            entities=[],
            metadata={"document_kind": kind, "has_ground_truth": False, "text_chars": len(text)},
            reference_output={"text": text[:4000]} if text else None,
        )


class EkaCareNoteAdapter(_EkaCareBase):
    """Clinical note generation dataset: narrative in, structured JSON out."""

    name = "ekacare_clinical_note_generation"
    record_type = "CLINICAL_NOTE"

    def load_records(self, limit: int | None = None) -> list[NormalisedRecord]:
        records: list[NormalisedRecord] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in JSON_SUFFIXES:
                for index, payload in enumerate(self._iter_json(path)):
                    narrative = _first_key(payload, ["conversation", "transcript", "narrative", "input", "note", "text", "dialogue"])
                    reference = _first_key(payload, ["output", "structured", "ground_truth", "annotation", "target", "json"])
                    record_id = self._record_id(payload, f"{path.stem}-{index}")
                    patient_id = self.dataset_patient_id(record_id)
                    records.append(
                        NormalisedRecord(
                            source_record_id=record_id,
                            record_type=self.record_type,
                            original_format="JSON",
                            original_location=str(path.relative_to(self.root)),
                            synthetic_patient_id=patient_id,
                            entities=_entities_from_structured(reference, patient_id, self.data_origin) if reference else [],
                            metadata={"narrative_chars": len(_flatten_text(narrative)), "has_ground_truth": bool(reference)},
                            reference_output={"narrative": _flatten_text(narrative)[:8000], "structured": reference},
                        )
                    )
            elif suffix in TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="replace")
                records.append(
                    NormalisedRecord(
                        source_record_id=path.stem,
                        record_type=self.record_type,
                        original_format="TEXT",
                        original_location=str(path.relative_to(self.root)),
                        synthetic_patient_id=self.dataset_patient_id(path.stem),
                        entities=[],
                        metadata={"narrative_chars": len(text), "has_ground_truth": False},
                        reference_output={"narrative": text[:8000]},
                    )
                )
        if limit:
            records = records[:limit]
        return [self.normalise_record(record) for record in records]


class EkaCareSummaryAdapter(_EkaCareBase):
    """Medical history summarisation dataset: history context plus reference summary."""

    name = "ekacare_medical_history_summarisation"
    record_type = "HISTORY_SUMMARY"

    def load_records(self, limit: int | None = None) -> list[NormalisedRecord]:
        records: list[NormalisedRecord] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in JSON_SUFFIXES:
                for index, payload in enumerate(self._iter_json(path)):
                    history = _first_key(payload, ["history", "medical_history", "input", "context", "records", "patient_history"])
                    reference = _first_key(payload, ["summary", "reference_summary", "output", "target", "ground_truth"])
                    record_id = self._record_id(payload, f"{path.stem}-{index}")
                    patient_id = self.dataset_patient_id(record_id)
                    records.append(
                        NormalisedRecord(
                            source_record_id=record_id,
                            record_type=self.record_type,
                            original_format="JSON",
                            original_location=str(path.relative_to(self.root)),
                            synthetic_patient_id=patient_id,
                            entities=[],
                            metadata={
                                "history_chars": len(_flatten_text(history)),
                                "reference_chars": len(_flatten_text(reference)),
                                "has_ground_truth": bool(reference),
                            },
                            reference_output={
                                "history": _flatten_text(history)[:8000],
                                "summary": _flatten_text(reference)[:8000],
                            },
                        )
                    )
            elif suffix in TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="replace")
                records.append(
                    NormalisedRecord(
                        source_record_id=path.stem,
                        record_type=self.record_type,
                        original_format="TEXT",
                        original_location=str(path.relative_to(self.root)),
                        synthetic_patient_id=self.dataset_patient_id(path.stem),
                        entities=[],
                        metadata={"history_chars": len(text), "has_ground_truth": False},
                        reference_output={"history": text[:8000]},
                    )
                )
        if limit:
            records = records[:limit]
        return [self.normalise_record(record) for record in records]

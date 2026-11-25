"""Shared adapter interface for dataset integration.

Every adapter inspects its own files, normalises records into the common
clinical schema and reports honestly what it could not read. Nothing here
invents fields: absent columns stay absent.
"""

from __future__ import annotations

import abc
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.db import new_id


class DatasetUnavailable(RuntimeError):
    """Raised when the local dataset files needed by an adapter are missing."""


@dataclass
class DatasetFile:
    path: Path
    kind: str
    size_bytes: int


@dataclass
class NormalisedRecord:
    """One dataset record converted to the common schema."""

    source_record_id: str
    record_type: str
    original_format: str
    original_location: str
    synthetic_patient_id: str | None = None
    entities: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    reference_output: dict[str, Any] | None = None

    def record_id(self) -> str:
        digest = hashlib.sha256(f"{self.source_record_id}:{self.original_location}".encode()).hexdigest()[:12]
        return new_id(f"drec_{digest}")


class BaseDatasetAdapter(abc.ABC):
    """Contract every dataset adapter implements."""

    name: str = "base"
    dataset_type: str = "unknown"
    source_url: str = ""
    licence: str = "See upstream dataset card"
    patient_prefix: str = "dataset:"
    data_origin: str = "CONTROLLED_TEST_FIXTURE"

    @property
    def title(self) -> str:
        """Human-readable dataset name used by the API and the dashboard."""
        return self.name.replace("_", " ").title()

    @property
    def description(self) -> str:
        """Short provenance description; never claims data that is not present."""
        return f"{self.dataset_type} dataset read from local files under {self.root}."

    def __init__(self, root: Path | None = None) -> None:
        from backend.config import settings

        self.root = Path(root) if root else settings.dataset_path / self.name

    # ------------------------------------------------------------ discovery
    def available(self) -> bool:
        return self.root.exists() and any(self.root.rglob("*"))

    def files(self) -> list[DatasetFile]:
        if not self.root.exists():
            return []
        found: list[DatasetFile] = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                found.append(DatasetFile(path=path, kind=path.suffix.lower().lstrip(".") or "unknown", size_bytes=path.stat().st_size))
        return found

    def inspect_dataset(self) -> dict:
        files = self.files()
        by_kind: dict[str, int] = {}
        for item in files:
            by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        return {
            "dataset": self.name,
            "dataset_type": self.dataset_type,
            "source_url": self.source_url,
            "licence": self.licence,
            "root": str(self.root),
            "available": bool(files),
            "file_count": len(files),
            "files_by_kind": by_kind,
            "sample_files": [str(item.path.relative_to(self.root)) for item in files[:8]],
            "note": "" if files else "No local files found. Place the dataset under this directory to enable import.",
        }

    # ------------------------------------------------------------- loading
    @abc.abstractmethod
    def load_records(self, limit: int | None = None) -> list[NormalisedRecord]:
        """Read the local files and return normalised records."""

    def normalise_record(self, record: NormalisedRecord) -> NormalisedRecord:
        for entity in record.entities:
            entity.setdefault("data_origin", self.data_origin)
            entity.setdefault("source_type", self.dataset_type)
            entity.setdefault("source_record_id", record.source_record_id)
            entity.setdefault("patient_id", record.synthetic_patient_id)
        return record

    def validate_record(self, record: NormalisedRecord) -> list[str]:
        problems: list[str] = []
        if not record.source_record_id:
            problems.append("missing source_record_id")
        if not record.record_type:
            problems.append("missing record_type")
        for entity in record.entities:
            if not entity.get("category"):
                problems.append("entity without category")
            if not entity.get("original_value") and not entity.get("normalized_value"):
                problems.append("entity without any value")
        return problems

    def get_source_metadata(self) -> dict:
        return {
            "name": self.name,
            "source_url": self.source_url,
            "licence": self.licence,
            "dataset_type": self.dataset_type,
            "data_origin": self.data_origin,
            "patient_prefix": self.patient_prefix,
        }

    # -------------------------------------------------------------- helpers
    def dataset_patient_id(self, source_patient_id: str) -> str:
        return f"{self.patient_prefix}{source_patient_id}"

    def _read_json(self, path: Path) -> Any:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return json.load(handle)

"""Registry of dataset adapters."""

from __future__ import annotations

from backend.datasets.base_adapter import BaseDatasetAdapter
from backend.datasets.ekacare_adapters import (
    EkaCareNoteAdapter,
    EkaCareParsingAdapter,
    EkaCareSummaryAdapter,
)
from backend.datasets.synthea_adapter import SyntheaAdapter

ADAPTERS: dict[str, type[BaseDatasetAdapter]] = {
    adapter.name: adapter
    for adapter in (
        SyntheaAdapter,
        EkaCareParsingAdapter,
        EkaCareNoteAdapter,
        EkaCareSummaryAdapter,
    )
}


def get_adapter(name: str) -> BaseDatasetAdapter:
    try:
        return ADAPTERS[name]()
    except KeyError as exc:
        raise KeyError(f"Unknown dataset '{name}'. Known datasets: {', '.join(sorted(ADAPTERS))}") from exc


def describe_adapters() -> list[dict]:
    described = []
    for name, adapter_cls in ADAPTERS.items():
        adapter = adapter_cls()
        inspection = adapter.inspect_dataset()
        described.append(
            {
                "name": name,
                "title": adapter.title,
                "dataset_type": adapter.dataset_type,
                "source_url": adapter.source_url,
                "licence": adapter.licence,
                "data_origin": adapter.data_origin,
                "available": inspection.get("available", False),
                "file_count": inspection.get("file_count", 0),
                "formats": inspection.get("formats", []),
                "notes": inspection.get("notes", []),
                "root": inspection.get("root"),
            }
        )
    return described

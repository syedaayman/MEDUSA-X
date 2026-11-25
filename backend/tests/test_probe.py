"""Environment probe used during bootstrap. Writes a JSON report into the repo."""

import importlib
import json
import sys
from pathlib import Path

MODULES = [
    "pydantic",
    "pydantic_settings",
    "fastapi",
    "starlette",
    "uvicorn",
    "multipart",
    "fitz",
    "pymupdf",
    "openai",
    "agents",
    "httpx",
    "pytest",
]


def test_probe_writes_report():
    report = {"python": sys.version, "executable": sys.executable, "modules": {}}
    for name in MODULES:
        try:
            module = importlib.import_module(name)
            report["modules"][name] = getattr(module, "__version__", "installed")
        except Exception as exc:  # noqa: BLE001 - probe reports everything
            report["modules"][name] = f"MISSING: {type(exc).__name__}"
    target = Path(__file__).with_name("_env_probe.json")
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert target.exists()

"""Pytest fixtures: every test runs against an isolated database and storage dir."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session", autouse=True)
def _isolated_environment():
    tmp = tempfile.mkdtemp(prefix="medusa-x-tests-")
    os.environ["DATABASE_PATH"] = str(Path(tmp) / "test.db")
    os.environ["STORAGE_DIR"] = str(Path(tmp) / "documents")
    os.environ["DATASET_DIR"] = str(Path(tmp) / "datasets")
    os.environ["OPENAI_API_KEY"] = ""
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def patient_id(request):
    return f"test-{request.node.name[:40]}"

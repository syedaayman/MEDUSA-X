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

# Redirect persistence BEFORE any backend module is imported. pytest imports
# test modules during collection, and `backend.config.settings` is created at
# import time, so the environment must be overridden at module level: os.environ
# values take precedence over the .env file, and a session-scoped fixture would
# be too late. This keeps every test on a private SQLite file, no real key.
_TEST_TMP = Path(tempfile.mkdtemp(prefix="medusa-x-tests-"))
os.environ["DATABASE_PATH"] = str(_TEST_TMP / "test.db")
os.environ["STORAGE_DIR"] = str(_TEST_TMP / "documents")
os.environ["DATASET_DIR"] = str(_TEST_TMP / "datasets")
os.environ["OPENAI_API_KEY"] = ""


@pytest.fixture(scope="session", autouse=True)
def _isolated_environment():
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

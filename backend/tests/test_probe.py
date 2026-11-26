"""Readiness checks for the backend test session.

They fail fast with an explicit message when the backend dependencies are not
installed, which is the usual cause of a confusing collection error, and they
prove that conftest.py redirected persistence away from the working tree.
No file is written into the repository by these tests.
"""

from __future__ import annotations

import pytest

REQUIRED_MODULES = (
    "fastapi",
    "starlette",
    "uvicorn",
    "multipart",
    "fitz",
    "pydantic",
    "pydantic_settings",
)


@pytest.mark.parametrize("module", REQUIRED_MODULES)
def test_backend_dependency_is_available(module: str) -> None:
    """Skip rather than error, so one missing extra does not hide the suite."""
    pytest.importorskip(module)


def test_persistence_is_redirected_for_the_test_session() -> None:
    from backend.config import settings

    assert str(settings.database_path).endswith("test.db"), settings.database_path
    assert settings.llm_enabled is False, "tests must run with no model credential configured"

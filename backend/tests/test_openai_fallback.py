"""Regression tests for OpenAI credit exhaustion and deterministic fallback."""

from __future__ import annotations

import asyncio
import time
import types

import openai
import pytest

from backend.agents import sdk_runtime


class _FakeSettings:
    def __init__(self, key="sk-fake-key"):
        self.openai_api_key = key
        self.llm_provider = "openai"
        self.openai_model = "gpt-4o-mini"
        self.max_agent_turns = 4
        self.agent_timeout_seconds = 30
        self.llm_enabled = bool(key)


def _make_rate_limit(message):
    # openai.RateLimitError requires a response; build a minimal one via httpx
    import httpx

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(429, request=request)
    return openai.RateLimitError(message, response=response, body={"error": {"message": message}})


def test_sdk_runtime_classifies_credit_exhaustion(monkeypatch):
    monkeypatch.setattr(sdk_runtime, "settings", _FakeSettings())
    monkeypatch.setattr(sdk_runtime, "SDK_AVAILABLE", True)
    monkeypatch.setattr(sdk_runtime, "Runner", types.SimpleNamespace(run=lambda *a, **k: (_ for _ in ()).throw(_make_rate_limit("You have no credits remaining"))))
    # Runner.run must be awaitable; wrap
    async def _raise(*a, **k):
        raise _make_rate_limit("You have no credits remaining")
    monkeypatch.setattr(sdk_runtime.Runner, "run", _raise)

    result = sdk_runtime.run_coordinator("p1", "run1")
    assert result["available"] is False
    assert result["kind"] == "credit_exhausted"
    assert result["reason"] == "AI model unavailable — continuing with deterministic clinical processing."


def test_sdk_runtime_classifies_missing_credentials(monkeypatch):
    monkeypatch.setattr(sdk_runtime, "settings", _FakeSettings(key=""))
    monkeypatch.setattr(sdk_runtime, "SDK_AVAILABLE", True)
    result = sdk_runtime.run_coordinator("p1", "run1")
    assert result["available"] is False
    assert result["kind"] == "missing_credentials"


def test_sdk_runtime_classifies_temporary_rate_limit(monkeypatch):
    monkeypatch.setattr(sdk_runtime, "settings", _FakeSettings())
    monkeypatch.setattr(sdk_runtime, "SDK_AVAILABLE", True)
    calls = {"n": 0}

    async def _raise(*a, **k):
        calls["n"] += 1
        raise _make_rate_limit("Rate limit exceeded, please retry")

    monkeypatch.setattr(sdk_runtime.Runner, "run", _raise)
    result = sdk_runtime.run_coordinator("p1", "run1")
    assert result["available"] is False
    assert result["kind"] == "rate_limited"
    # Retried exactly once
    assert calls["n"] == 2


def test_orchestrator_falls_back_on_credit_exhaustion(monkeypatch, client):
    from backend.agents import orchestrator, sdk_runtime

    def _fake_coordinator(patient_id, run_id, focus=""):
        return {
            "engine": "agents_sdk",
            "available": False,
            "kind": "credit_exhausted",
            "reason": "AI model unavailable — continuing with deterministic clinical processing.",
            "tool_calls": 0,
        }

    monkeypatch.setattr(sdk_runtime, "run_coordinator", _fake_coordinator)
    monkeypatch.setattr(orchestrator.sdk_runtime, "run_coordinator", _fake_coordinator)
    # Make the orchestrator believe the model layer is configured so the
    # credit-exhaustion branch (which appends the warning) is exercised.
    monkeypatch.setattr(orchestrator, "settings", types.SimpleNamespace(llm_enabled=True))

    import fitz

    def make_pdf(lines):
        doc = fitz.open()
        page = doc.new_page()
        y = 72
        for line in lines:
            page.insert_text((72, y), line, fontsize=10)
            y += 16
        blob = doc.tobytes()
        doc.close()
        return blob

    DOC_A = ["Discharge Summary", "Patient: T", "Date: 2024-03-01", "Diagnosis: Hypertension"]
    response = client.post(
        "/api/upload",
        data={"patient_id": "credit-test-p", "start_analysis": "true", "reprocess": "false"},
        files=[("files", ("d.pdf", make_pdf(DOC_A), "application/pdf"))],
    )
    assert response.status_code == 200
    run_id = response.json()["analysis_run_id"]

    deadline = time.time() + 60
    body = {}
    while time.time() < deadline:
        body = client.get(f"/api/analysis/{run_id}").json()
        if body.get("status") in {"COMPLETED", "PARTIAL", "FAILED"}:
            break
        time.sleep(0.2)
    assert body.get("status") in {"COMPLETED", "PARTIAL"}, body
    assert body.get("engine") == "deterministic", body.get("engine")
    warnings = body.get("warnings") or []
    assert any("AI model unavailable — continuing with deterministic clinical processing." in str(w) for w in warnings), warnings

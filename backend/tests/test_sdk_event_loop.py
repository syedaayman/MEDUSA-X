"""Regression tests for the OpenAI Agents SDK model-layer event-loop lifecycle.

The coordinator used to call ``asyncio.run`` for every model-layer turn, which
creates and closes a fresh event loop per call. The Agents SDK shares module-level
async HTTP clients bound to the loop used first, so runs after the first failed with
``RuntimeError: Event loop is closed`` and the orchestrator reported
``Model layer unavailable: RuntimeError: Event loop is closed``.
"""

from __future__ import annotations

import asyncio

from backend.agents import sdk_runtime


class _FakeSettings:
    def __init__(self, key: str = "sk-fake-key") -> None:
        self.openai_api_key = key
        self.llm_provider = "openai"
        self.openai_model = "gpt-4o-mini"
        self.max_agent_turns = 4
        self.agent_timeout_seconds = 30
        self.llm_enabled = bool(key)


class _FakeRunResult:
    final_output = "fake coordination note"


def _install_fake_model_layer(monkeypatch) -> None:
    monkeypatch.setattr(sdk_runtime, "settings", _FakeSettings())
    monkeypatch.setattr(sdk_runtime, "SDK_AVAILABLE", True)
    monkeypatch.setattr(
        sdk_runtime,
        "build_specialists",
        lambda ctx: {"orchestrator": object(), "specialists": {}},
    )

    async def _fake_run(*args, **kwargs):
        return _FakeRunResult()

    monkeypatch.setattr(sdk_runtime.Runner, "run", _fake_run)


def test_coordinator_reuses_a_single_persistent_event_loop(monkeypatch):
    monkeypatch.setattr(sdk_runtime, "_COORDINATOR_LOOP", None)
    _install_fake_model_layer(monkeypatch)

    loops: list[asyncio.AbstractEventLoop] = []

    async def _recording_run(*args, **kwargs):
        loops.append(asyncio.get_running_loop())
        return _FakeRunResult()

    monkeypatch.setattr(sdk_runtime.Runner, "run", _recording_run)

    first = sdk_runtime.run_coordinator("p1", "run1")
    second = sdk_runtime.run_coordinator("p2", "run2")

    assert first["available"] is True
    assert second["available"] is True
    assert first["kind"] == "ok"
    assert second["kind"] == "ok"

    # Regression guard: consecutive coordinator runs must share one event loop.
    # A fresh loop per run (previous asyncio.run behaviour) rebinds the shared
    # OpenAI HTTP client to a closed loop and raises "Event loop is closed".
    assert loops[0] is loops[1]

    loop = sdk_runtime._coordinator_loop()
    assert not loop.is_closed()


def test_coordinator_loop_stays_reusable_across_multiple_runs(monkeypatch):
    monkeypatch.setattr(sdk_runtime, "_COORDINATOR_LOOP", None)
    _install_fake_model_layer(monkeypatch)

    for index, patient_id in enumerate(("p1", "p2", "p3"), start=1):
        result = sdk_runtime.run_coordinator(patient_id, f"run-{index}")
        assert result["available"] is True
        assert result["kind"] == "ok"

    loop = sdk_runtime._coordinator_loop()
    assert not loop.is_closed()
    assert not loop.is_running()

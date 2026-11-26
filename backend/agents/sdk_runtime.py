"""OpenAI Agents SDK runtime for the specialist team.

The deterministic pipeline is always the source of truth for stored clinical
facts. When an API key is configured, these agents add genuine model-driven
coordination on top of the stored evidence: they choose which tools to call,
read original pages and can escalate findings. Without a key the platform keeps
working and reports that the model layer is disabled, rather than pretending.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from backend.agents import tools as agent_tools
from backend.config import settings

try:  # pragma: no cover - depends on the optional SDK install
    from agents import Agent, Runner, function_tool

    SDK_AVAILABLE = True
    SDK_IMPORT_ERROR: str | None = None
except Exception as exc:  # noqa: BLE001 - optional dependency
    Agent = Runner = function_tool = None  # type: ignore[assignment]
    SDK_AVAILABLE = False
    SDK_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


SAFETY_RULES = (
    "You are a clinical record reconciliation assistant inside a prototype. "
    "Never invent a diagnosis, medication, dose, laboratory value, date, page number or quotation. "
    "Never decide which record is clinically correct and never recommend treatment. "
    "Every statement must be traceable to a tool result from this run. "
    "If evidence is missing or ambiguous, say so and route the finding to human review. "
    "Distinguish a legitimate change over time from a possible inconsistency."
)

SPECIALIST_INSTRUCTIONS = {
    "DOCUMENT_INTELLIGENCE": (
        "Classify each document, report its clinical date (never the upload date), the sections present, "
        "the pages that matter and anything unreadable. Flag OCR_REQUIRED pages instead of guessing."
    ),
    "CLINICAL_STRUCTURING": (
        "Extract diagnoses, medications with dose/route/frequency, allergies, laboratory values with units, "
        "procedures and vitals. Preserve the original wording and source page. Represent unknown values as null."
    ),
    "RECONCILIATION": (
        "Compare like with like across documents for the same patient. Consider clinical dates before flagging "
        "anything. Do not treat a chronological dose change as a contradiction, and do not treat missing "
        "information as a contradiction. Report each proposal with both compared values and sources."
    ),
    "EVIDENCE_VERIFICATION": (
        "Independently re-read the cited pages for each proposed discrepancy. Confirm both values exist, that the "
        "pages and documents belong to this patient and that the dates are consistent. Answer with exactly one of "
        "VERIFIED_POTENTIAL_CONFLICT, NOT_A_CONFLICT, INSUFFICIENT_EVIDENCE or NEEDS_HUMAN_REVIEW."
    ),
    "TIMELINE_SUMMARY": (
        "Order events chronologically, keep date precision and uncertainty, separate current from historical "
        "information and cite document plus page for every event. Summarise only what the records contain."
    ),
}


def _build_tools(ctx: agent_tools.ToolContext) -> list[Any]:
    """Expose the real tool functions to the SDK, bound to one patient context."""

    def get_patient_context() -> str:
        """Patient identifier, documents and entity counts."""
        return json.dumps(agent_tools.get_patient_context(ctx), default=str)[:6000]

    def read_document(document_id: str) -> str:
        """Read the extracted text of one document (bounded)."""
        return json.dumps(agent_tools.read_document(ctx, document_id), default=str)[:8000]

    def get_document_page(document_id: str, page_number: int) -> str:
        """Read one original page of a document."""
        return json.dumps(agent_tools.get_document_page(ctx, document_id, page_number), default=str)[:6000]

    def search_patient_records(query: str) -> str:
        """Search this patient's pages for a phrase and return page-level matches."""
        return json.dumps(agent_tools.search_patient_records(ctx, query), default=str)[:6000]

    def get_clinical_entities(category: str | None = None) -> str:
        """Stored structured entities for this patient, optionally by category."""
        return json.dumps(agent_tools.get_clinical_entities(ctx, category), default=str)[:8000]

    def compare_records() -> str:
        """Propose potential discrepancies across this patient's documents."""
        return json.dumps(agent_tools.compare_records(ctx), default=str)[:8000]

    def verify_evidence(conflict_id: str) -> str:
        """Independently verify one proposed discrepancy against the original pages."""
        return json.dumps(agent_tools.verify_evidence(ctx, conflict_id), default=str)[:4000]

    def build_patient_timeline() -> str:
        """Rebuild the chronological timeline from stored entities."""
        return json.dumps(agent_tools.build_patient_timeline(ctx), default=str)[:6000]

    def request_human_review(conflict_id: str, reason: str) -> str:
        """Escalate a finding to a human reviewer with a reason."""
        return json.dumps(agent_tools.request_human_review(ctx, conflict_id, reason), default=str)[:2000]

    return [
        function_tool(get_patient_context),
        function_tool(read_document),
        function_tool(get_document_page),
        function_tool(search_patient_records),
        function_tool(get_clinical_entities),
        function_tool(compare_records),
        function_tool(verify_evidence),
        function_tool(build_patient_timeline),
        function_tool(request_human_review),
    ]


def build_specialists(ctx: agent_tools.ToolContext) -> dict[str, Any]:
    """Create the five specialist agents plus the manager that coordinates them."""
    tools = _build_tools(ctx)
    specialists = {
        name: Agent(
            name=f"MEDUSA-X {name.replace('_', ' ').title()}",
            model=settings.openai_model,
            instructions=f"{SAFETY_RULES}\n\n{instruction}",
            tools=tools,
        )
        for name, instruction in SPECIALIST_INSTRUCTIONS.items()
    }
    orchestrator = Agent(
        name="MEDUSA-X Orchestrator",
        model=settings.openai_model,
        instructions=(
            f"{SAFETY_RULES}\n\n"
            "You are the orchestrator of a clinical record reconciliation team. You keep control: inspect the "
            "patient context first, then decide which specialists are needed. With a single document, structure it "
            "and build a timeline; do not invent cross-document conflicts. With several comparable records, compare "
            "them and verify every proposal against the original pages. Report, in plain language, what you did, "
            "which tools returned what, which findings were verified, which were rejected and which need a human. "
            "Never claim an agent ran unless its tool returned a result."
        ),
        tools=tools,
        handoffs=list(specialists.values()),
    )
    return {"orchestrator": orchestrator, "specialists": specialists}


CREDIT_EXHAUSTED_MESSAGE = "AI model unavailable — continuing with deterministic clinical processing."


def _classify_error(exc: Exception) -> tuple[str, str]:
    """Classify a model-layer failure into a kind and a user-facing reason.

    Kinds: missing_credentials, credit_exhausted, rate_limited, other_error.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    # Missing credentials
    if "api_key" in text or "credentials" in text or "authentication" in text or "401" in text:
        return "missing_credentials", "OPENAI_API_KEY is not configured or invalid; deterministic agents ran instead."
    # Credit exhaustion (do not retry)
    if isinstance(exc, Exception) and (
        "no credits" in text
        or "credits remaining" in text
        or "insufficient_quota" in text
        or "quota" in text
        or "billing" in text
        or "exceeded your current quota" in text
    ):
        return "credit_exhausted", CREDIT_EXHAUSTED_MESSAGE
    # Temporary rate limiting
    if "rate" in text and "limit" in text:
        return "rate_limited", "Temporary OpenAI rate limit; continuing with deterministic clinical processing."
    return "other_error", f"{type(exc).__name__}: {exc}"[:500]


def run_coordinator(patient_id: str, run_id: str, focus: str = "") -> dict:
    """Run the model-driven coordinator over one patient's stored records."""
    if not SDK_AVAILABLE:
        return {
            "engine": "deterministic",
            "available": False,
            "kind": "sdk_unavailable",
            "reason": f"OpenAI Agents SDK not installed ({SDK_IMPORT_ERROR})",
        }
    if not settings.llm_enabled:
        return {
            "engine": "deterministic",
            "available": False,
            "kind": "missing_credentials",
            "reason": "OPENAI_API_KEY is not configured; deterministic agents ran instead.",
        }

    if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key

    # The Agents SDK resolves its default OpenAI client from the OPENAI_API_KEY
    # environment variable. Settings may have loaded the key from backend/.env
    # without it reaching os.environ, so propagate it here (never log it).
    if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key

    ctx = agent_tools.ToolContext(run_id=run_id, patient_id=patient_id, agent="ORCHESTRATOR")
    team = build_specialists(ctx)
    prompt = (
        f"Coordinate a reconciliation review for patient {patient_id}. "
        "Start with get_patient_context, then use the tools you need. "
        "Finish with a short evidence-based coordination note: what was checked, what was verified, "
        "what was rejected, what needs human review, and any remaining uncertainty."
    )
    if focus:
        prompt += f" Additional focus from the operator: {focus}"

    async def _run() -> Any:
        return await asyncio.wait_for(
            Runner.run(team["orchestrator"], prompt, max_turns=settings.max_agent_turns),
            timeout=settings.agent_timeout_seconds,
        )

    # Retry only for temporary rate limits (bounded, single retry). Credit
    # exhaustion and other failures fall back immediately without retrying.
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            result = asyncio.run(_run())
            output = getattr(result, "final_output", None) or ""
            return {
                "engine": "agents_sdk",
                "available": True,
                "kind": "ok",
                "note": str(output)[:6000],
                "tool_calls": len(ctx.calls),
            }
        except Exception as exc:  # noqa: BLE001 - model layer is optional
            last_exc = exc
            kind, _ = _classify_error(exc)
            if kind != "rate_limited" or attempt == 1:
                break
    assert last_exc is not None
    kind, reason = _classify_error(last_exc)
    return {
        "engine": "agents_sdk",
        "available": False,
        "kind": kind,
        "reason": reason,
        "tool_calls": len(ctx.calls),
    }

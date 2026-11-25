"""Configurable, explicitly invoked LLM provider interface."""

from openai import AsyncOpenAI

from backend.config import settings


async def generate_text(prompt: str) -> str:
    """Generate text through the configured provider when credentials are present."""
    if not settings.openai_api_key:
        raise RuntimeError("Set OPENAI_API_KEY before invoking the LLM service.")
    if settings.llm_provider.lower() != "openai":
        raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.create(model=settings.openai_model, input=prompt)
    return response.output_text

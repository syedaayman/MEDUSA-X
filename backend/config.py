"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Configuration loaded from environment variables and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Persistence: SQLite is the default store. Set MEDUSA_DB_PATH to relocate it.
    database_path: str = str(BACKEND_DIR / "data" / "medusa_x.db")
    storage_dir: str = str(BACKEND_DIR / "data" / "documents")
    dataset_dir: str = str(REPO_ROOT / "sample_data" / "datasets")

    # Bounded agent execution.
    max_agent_turns: int = 14
    max_specialist_retries: int = 1
    agent_timeout_seconds: int = 180
    max_upload_bytes: int = 20 * 1024 * 1024
    max_document_chars_for_model: int = 6000

    @property
    def cors_origin_list(self) -> list[str]:
        """Return configured CORS origins as a trimmed list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def llm_enabled(self) -> bool:
        """True when a backend-only OpenAI credential is configured."""
        return bool(self.openai_api_key.strip()) and self.llm_provider.lower() == "openai"

    @property
    def database_file(self) -> Path:
        return Path(self.database_path)

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir)

    @property
    def dataset_path(self) -> Path:
        return Path(self.dataset_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

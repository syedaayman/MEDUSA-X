"""Environment-backed application settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables and an optional .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    supabase_url: str = ""
    supabase_secret_key: str = ""
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    @property
    def cors_origin_list(self) -> list[str]:
        """Return configured CORS origins as a trimmed list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

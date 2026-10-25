## Configuration code
"""Application settings, loaded from environment variables or a local .env file."""

# Imports
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# The Settings class
class Settings(BaseSettings):
    """All configuration lives here, so no secrets are hard-coded in the code."""

    # Configuration loading
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unknown variables instead of crashing
    )

    # Application environment and logging
    app_env: str = "development"  # development | production
    log_level: str = "INFO"

    # API keys
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"  # chosen from the official model pages, 24 Oct 2026
    groq_model: str = "openai/gpt-oss-120b"  # backup


# Cached settings function
@lru_cache
def get_settings() -> Settings:
    """Return one shared Settings object (created on first use)."""
    return Settings()

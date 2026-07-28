"""Application settings, loaded from the environment / `.env`."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # `model_` is a protected namespace in pydantic v2; our settings use the
        # AIVOA_MODEL_* prefix, so the warning has to be switched off.
        protected_namespaces=(),
    )

    # --- Groq ---------------------------------------------------------------
    groq_api_key: str = ""

    # --- Model roles --------------------------------------------------------
    aivoa_model_router: str = "gemma2-9b-it"
    aivoa_model_extractor: str = "gemma2-9b-it"
    aivoa_model_reasoner: str = "llama-3.3-70b-versatile"
    aivoa_model_auto_fallback: bool = True

    # --- Database -----------------------------------------------------------
    database_url: str = ""

    # --- App ----------------------------------------------------------------
    aivoa_cors_origins: str = "http://localhost:5173"
    aivoa_log_level: str = "INFO"
    aivoa_max_upload_mb: int = 10

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.aivoa_cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.aivoa_max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()

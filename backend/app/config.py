from functools import lru_cache
from typing import Optional
from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PolicyPilot API"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] | str = ["http://localhost:3000"]
    database_url: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[SecretStr] = None
    supabase_anon_key: Optional[SecretStr] = None
    policy_storage_bucket: str = "policy-documents"
    max_policy_file_size_bytes: int = 10 * 1024 * 1024
    storage_signed_url_expiry: int = 300
    openai_api_key: Optional[SecretStr] = None
    openai_base_url: str = "http://localhost:11434/v1"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    embedding_timeout_seconds: float = 30.0
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0
    chunk_size_chars: int = 1000
    chunk_overlap_chars: int = 200

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                import json
                try:
                    return json.loads(v_str)
                except Exception:
                    pass
            return [origin.strip() for origin in v_str.split(",") if origin.strip()]
        return v  # type: ignore[return-value]

    @model_validator(mode="after")
    def _normalise_database_url(self) -> "Settings":
        if self.database_url:
            clean = self.database_url.strip()
            for p in ("postgresql://", "postgres://"):
                if clean.startswith(p):
                    clean = "postgresql+asyncpg://" + clean[len(p):]
                    break
            object.__setattr__(self, "database_url", clean)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

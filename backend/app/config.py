from functools import lru_cache
from typing import Optional
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PolicyPilot API"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]
    database_url: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[SecretStr] = None

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _normalise_database_url(self) -> "Settings":
        if self.database_url:
            for p in ("postgresql://", "postgres://"):
                if self.database_url.startswith(p):
                    object.__setattr__(self, "database_url", "postgresql+asyncpg://" + self.database_url[len(p):])
                    break
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

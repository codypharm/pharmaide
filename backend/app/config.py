"""Centralised env-driven configuration for the backend.

Keeps every PHARMAIDE_* environment knob in one place so that wiring (logging,
checkpointer paths, debug gates) reads the same values everywhere.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": silently drop unknown env vars instead of raising. Cloud
    # Run injects platform vars (PORT, K_SERVICE, etc.) that are not ours.
    model_config = SettingsConfigDict(env_prefix="PHARMAIDE_", env_file=".env", extra="ignore")

    checkpoint_db_path: str = "./pharmaide.db"

    # Default points at the local docker-compose Postgres. Override via
    # PHARMAIDE_DATABASE_URL in CI or any deployed environment.
    database_url: str = "postgresql+asyncpg://pharmaide:pharmaide@localhost:5432/pharmaide"

    # Defaults to False so a forgotten env var in any deployed environment
    # leaves the dev-only /debug/graph route unmounted, not exposed.
    debug_routes_enabled: bool = False

    log_mode: Literal["console", "json"] = "console"

    rxnorm_base_url: str = "https://rxnav.nlm.nih.gov/REST"

    openai_api_key: SecretStr | None = None

    # Explicit safety-provider mode. "model" is the current interim path using
    # typed PydanticAI checks; "unconfigured" deliberately fails closed.
    safety_provider: Literal["model", "unconfigured"] = "model"

    # Caps a single analysis run so a stuck graph cannot pin background
    # capacity indefinitely. Route-level test overrides use the same bounds.
    analysis_timeout_seconds: int = Field(default=60, gt=0, le=300)

    # Temporary pre-auth guard. Once GCIP lands, the route will use the real
    # actor id instead of the X-Pharmaide-User-Id development header.
    max_concurrent_analyses_per_user: int = Field(default=3, gt=0, le=50)

    # Local development storage for uploaded KB source files. Production should
    # point this adapter at blob storage while keeping the DB metadata contract.
    knowledge_upload_dir: str = "./data/kb_uploads"
    knowledge_max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    knowledge_ingestion_stale_minutes: int = Field(default=30, gt=0, le=24 * 60)

    @field_validator("knowledge_max_upload_bytes", mode="before")
    @classmethod
    def parse_upload_size(cls, value: object) -> object:
        """Accept byte counts and operator-friendly size strings like 25MB."""
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower().replace(" ", "")
        if normalized.isdigit():
            return int(normalized)
        units = {
            "kb": 1024,
            "kib": 1024,
            "mb": 1024 * 1024,
            "mib": 1024 * 1024,
        }
        for suffix, multiplier in units.items():
            if normalized.endswith(suffix):
                number = normalized[: -len(suffix)]
                if number.isdigit():
                    return int(number) * multiplier
        return value


# lru_cache so Settings is parsed once per process. Cheap insurance against
# re-reading the .env file on every Depends(get_settings) call.
@lru_cache
def get_settings() -> Settings:
    return Settings()

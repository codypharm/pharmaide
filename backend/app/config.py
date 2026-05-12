"""Centralised env-driven configuration for the backend.

Keeps every PHARMAIDE_* environment knob in one place so that wiring (logging,
checkpointer paths, debug gates) reads the same values everywhere.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
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


# lru_cache so Settings is parsed once per process. Cheap insurance against
# re-reading the .env file on every Depends(get_settings) call.
@lru_cache
def get_settings() -> Settings:
    return Settings()

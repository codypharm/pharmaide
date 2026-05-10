from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PHARMAIDE_", env_file=".env", extra="ignore")

    checkpoint_db_path: str = "./pharmaide.db"
    debug_routes_enabled: bool = False
    log_mode: Literal["console", "json"] = "console"


@lru_cache
def get_settings() -> Settings:
    return Settings()

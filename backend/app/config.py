"""Centralised env-driven configuration for the backend.

Keeps every PHARMAIDE_* environment knob in one place so that wiring (logging,
checkpointer paths, debug gates) reads the same values everywhere.
"""

from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
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

    cors_allowed_origins: str = "http://localhost:5173"

    log_mode: Literal["console", "json"] = "console"

    # disabled keeps local/dev compatibility with X-Pharmaide-User-Id.
    # gcip requires Authorization: Bearer <Firebase/GCIP ID token>.
    auth_mode: Literal["disabled", "gcip"] = "disabled"
    gcip_project_id: str | None = None
    gcip_workspace_claim: str = "workspace_id"
    gcip_require_workspace_claim: bool = False
    gcip_workspace_memberships_claim: str = "workspace_memberships"
    gcip_require_workspace_membership: bool = False

    rxnorm_base_url: str = "https://rxnav.nlm.nih.gov/REST"

    openai_api_key: SecretStr | None = None

    # Explicit safety-provider mode. "model" is the current interim path using
    # typed PydanticAI checks; "remote_http" calls a private safety gateway;
    # "unconfigured" deliberately fails closed.
    safety_provider: Literal["model", "remote_http", "unconfigured"] = "model"
    llama_guard_url: str | None = None
    agentdog_url: str | None = None
    safety_provider_api_key: SecretStr | None = None
    safety_provider_timeout_seconds: float = Field(default=10, gt=0, le=60)

    whatsapp_webhook_verify_token: SecretStr | None = None
    whatsapp_webhook_app_secret: SecretStr | None = None
    whatsapp_delivery_provider: Literal["placeholder", "cloud_api"] = "placeholder"
    whatsapp_cloud_api_access_token: SecretStr | None = None
    whatsapp_cloud_api_phone_number_id: str | None = None
    whatsapp_workspace_scope_id: UUID | None = None
    whatsapp_cloud_api_version: str = "v25.0"
    whatsapp_cloud_api_base_url: str = "https://graph.facebook.com"

    # Caps a single analysis run so a stuck graph cannot pin background
    # capacity indefinitely. Route-level test overrides use the same bounds.
    analysis_timeout_seconds: int = Field(default=60, gt=0, le=300)

    # Caps active analyses per actor/workspace so one caller cannot saturate
    # the analysis worker pool.
    max_concurrent_analyses_per_user: int = Field(default=3, gt=0, le=50)

    # Local development storage for uploaded KB source files. Production will
    # select a durable adapter while keeping the same DB metadata contract.
    knowledge_storage_backend: Literal["local"] = "local"
    knowledge_upload_dir: str = "./data/kb_uploads"
    knowledge_max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    knowledge_ingestion_stale_minutes: int = Field(default=30, gt=0, le=24 * 60)

    # Closed treatments are only purge-eligible after they are archived and this
    # retention window has elapsed.
    data_retention_closed_treatment_days: int = Field(default=365, ge=0, le=3650)

    # Internal worker routes are open in local dev, but production should require
    # Google-issued OIDC identity tokens from Cloud Tasks/Scheduler invokers.
    internal_worker_auth: Literal["disabled", "oidc"] = "disabled"
    internal_worker_audience: str | None = None

    # In-process is the safe local default. Production will switch this to
    # Cloud Tasks once the durable queue client is wired.
    task_backend: Literal["in_process", "cloud_tasks"] = "in_process"
    cloud_tasks_queue_path: str | None = None
    cloud_tasks_base_url: str | None = None
    cloud_tasks_service_account_email: str | None = None
    cloud_tasks_oidc_audience: str | None = None

    @field_validator("whatsapp_workspace_scope_id", mode="before")
    @classmethod
    def blank_workspace_scope_id_is_unset(cls, value: object) -> object:
        """Allow optional UUID env values to be left blank in local .env files."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

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

    @property
    def cors_allowed_origin_list(self) -> tuple[str, ...]:
        """Parse comma-separated browser origins from deployment env."""
        return tuple(
            origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()
        )

    @model_validator(mode="after")
    def require_remote_safety_urls(self) -> "Settings":
        """Remote safety mode needs both private provider endpoints."""
        if self.safety_provider == "remote_http" and (
            not self.llama_guard_url or not self.agentdog_url
        ):
            raise ValueError("remote_http safety provider requires both safety URLs")
        return self

    @model_validator(mode="after")
    def require_cloud_tasks_configuration(self) -> "Settings":
        """Cloud Tasks mode needs enough target metadata to enqueue safely."""
        if self.task_backend == "cloud_tasks" and (
            not self.cloud_tasks_queue_path
            or not self.cloud_tasks_base_url
            or not self.cloud_tasks_service_account_email
            or not self.cloud_tasks_oidc_audience
        ):
            raise ValueError(
                "cloud_tasks task backend requires queue path, base URL, "
                "service account email, and OIDC audience"
            )
        return self

    @model_validator(mode="after")
    def require_whatsapp_cloud_api_configuration(self) -> "Settings":
        """Real WhatsApp mode needs outbound credentials and signed inbound webhooks."""
        if self.whatsapp_delivery_provider == "cloud_api" and (
            not self.whatsapp_cloud_api_access_token
            or not self.whatsapp_cloud_api_phone_number_id
            or not self.whatsapp_webhook_verify_token
            or not self.whatsapp_webhook_app_secret
        ):
            raise ValueError(
                "cloud_api WhatsApp delivery requires token, phone number id, "
                "webhook verify token, and app secret"
            )
        return self

    @model_validator(mode="after")
    def require_internal_worker_audience(self) -> "Settings":
        """OIDC internal worker auth needs the expected token audience."""
        if self.internal_worker_auth == "oidc" and not self.internal_worker_audience:
            raise ValueError("oidc internal worker auth requires an audience")
        return self

    @model_validator(mode="after")
    def require_gcip_project_id(self) -> "Settings":
        """GCIP mode needs the project id used as the Firebase token audience."""
        if self.auth_mode == "gcip" and not self.gcip_project_id:
            raise ValueError("gcip auth mode requires a GCIP project id")
        return self


# lru_cache so Settings is parsed once per process. Cheap insurance against
# re-reading the .env file on every Depends(get_settings) call.
@lru_cache
def get_settings() -> Settings:
    return Settings()

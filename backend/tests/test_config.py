import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_defaults_match_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "PHARMAIDE_LOG_MODE",
        "PHARMAIDE_DEBUG_ROUTES_ENABLED",
        "PHARMAIDE_CORS_ALLOWED_ORIGINS",
        "PHARMAIDE_AUTH_MODE",
        "PHARMAIDE_GCIP_PROJECT_ID",
        "PHARMAIDE_CHECKPOINT_DB_PATH",
        "PHARMAIDE_RXNORM_BASE_URL",
        "PHARMAIDE_OPENAI_API_KEY",
        "PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN",
        "PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET",
        "PHARMAIDE_WHATSAPP_DELIVERY_PROVIDER",
        "PHARMAIDE_WHATSAPP_CLOUD_API_ACCESS_TOKEN",
        "PHARMAIDE_WHATSAPP_CLOUD_API_PHONE_NUMBER_ID",
        "PHARMAIDE_WHATSAPP_CLOUD_API_VERSION",
        "PHARMAIDE_WHATSAPP_CLOUD_API_BASE_URL",
        "PHARMAIDE_SAFETY_PROVIDER",
        "PHARMAIDE_LLAMA_GUARD_URL",
        "PHARMAIDE_AGENTDOG_URL",
        "PHARMAIDE_SAFETY_PROVIDER_API_KEY",
        "PHARMAIDE_SAFETY_PROVIDER_TIMEOUT_SECONDS",
        "PHARMAIDE_ANALYSIS_TIMEOUT_SECONDS",
        "PHARMAIDE_MAX_CONCURRENT_ANALYSES_PER_USER",
        "PHARMAIDE_KNOWLEDGE_UPLOAD_DIR",
        "PHARMAIDE_KNOWLEDGE_MAX_UPLOAD_BYTES",
        "PHARMAIDE_KNOWLEDGE_INGESTION_STALE_MINUTES",
        "PHARMAIDE_INTERNAL_WORKER_AUTH",
        "PHARMAIDE_INTERNAL_WORKER_AUDIENCE",
        "PHARMAIDE_TASK_BACKEND",
        "PHARMAIDE_CLOUD_TASKS_QUEUE_PATH",
        "PHARMAIDE_CLOUD_TASKS_BASE_URL",
        "PHARMAIDE_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL",
        "PHARMAIDE_CLOUD_TASKS_OIDC_AUDIENCE",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.log_mode == "console"
    assert settings.debug_routes_enabled is False
    assert settings.cors_allowed_origin_list == ("http://localhost:5173",)
    assert settings.auth_mode == "disabled"
    assert settings.gcip_project_id is None
    assert settings.checkpoint_db_path == "./pharmaide.db"
    assert settings.rxnorm_base_url == "https://rxnav.nlm.nih.gov/REST"
    assert settings.openai_api_key is None
    assert settings.whatsapp_webhook_verify_token is None
    assert settings.whatsapp_webhook_app_secret is None
    assert settings.whatsapp_delivery_provider == "placeholder"
    assert settings.whatsapp_cloud_api_access_token is None
    assert settings.whatsapp_cloud_api_phone_number_id is None
    assert settings.whatsapp_cloud_api_version == "v25.0"
    assert settings.whatsapp_cloud_api_base_url == "https://graph.facebook.com"
    assert settings.safety_provider == "model"
    assert settings.llama_guard_url is None
    assert settings.agentdog_url is None
    assert settings.safety_provider_api_key is None
    assert settings.safety_provider_timeout_seconds == 10
    assert settings.analysis_timeout_seconds == 60
    assert settings.max_concurrent_analyses_per_user == 3
    assert settings.knowledge_upload_dir == "./data/kb_uploads"
    assert settings.knowledge_max_upload_bytes == 25 * 1024 * 1024
    assert settings.knowledge_ingestion_stale_minutes == 30
    assert settings.internal_worker_auth == "disabled"
    assert settings.internal_worker_audience is None
    assert settings.task_backend == "in_process"
    assert settings.cloud_tasks_queue_path is None
    assert settings.cloud_tasks_base_url is None
    assert settings.cloud_tasks_service_account_email is None
    assert settings.cloud_tasks_oidc_audience is None


def test_settings_reads_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMAIDE_LOG_MODE", "json")
    monkeypatch.setenv("PHARMAIDE_DEBUG_ROUTES_ENABLED", "true")
    monkeypatch.setenv(
        "PHARMAIDE_CORS_ALLOWED_ORIGINS",
        "https://app.example, https://admin.example",
    )
    monkeypatch.setenv("PHARMAIDE_AUTH_MODE", "gcip")
    monkeypatch.setenv("PHARMAIDE_GCIP_PROJECT_ID", "pharmaide-staging")
    monkeypatch.setenv("PHARMAIDE_CHECKPOINT_DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("PHARMAIDE_RXNORM_BASE_URL", "https://rxnav.test/REST")
    monkeypatch.setenv("PHARMAIDE_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN", "verify-me")
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET", "app-secret")
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_DELIVERY_PROVIDER", "cloud_api")
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_CLOUD_API_ACCESS_TOKEN", "wa-token")
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_CLOUD_API_PHONE_NUMBER_ID", "phone-number-id")
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_CLOUD_API_VERSION", "v24.0")
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_CLOUD_API_BASE_URL", "https://graph.test")
    monkeypatch.setenv("PHARMAIDE_SAFETY_PROVIDER", "remote_http")
    monkeypatch.setenv("PHARMAIDE_LLAMA_GUARD_URL", "https://safety.test/v1/guard/check")
    monkeypatch.setenv("PHARMAIDE_AGENTDOG_URL", "https://safety.test/v1/referee/review")
    monkeypatch.setenv("PHARMAIDE_SAFETY_PROVIDER_API_KEY", "safety-test")
    monkeypatch.setenv("PHARMAIDE_SAFETY_PROVIDER_TIMEOUT_SECONDS", "8")
    monkeypatch.setenv("PHARMAIDE_ANALYSIS_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("PHARMAIDE_MAX_CONCURRENT_ANALYSES_PER_USER", "5")
    monkeypatch.setenv("PHARMAIDE_KNOWLEDGE_UPLOAD_DIR", "/tmp/kb")
    monkeypatch.setenv("PHARMAIDE_KNOWLEDGE_MAX_UPLOAD_BYTES", "1024")
    monkeypatch.setenv("PHARMAIDE_KNOWLEDGE_INGESTION_STALE_MINUTES", "7")
    monkeypatch.setenv("PHARMAIDE_INTERNAL_WORKER_AUTH", "oidc")
    monkeypatch.setenv("PHARMAIDE_INTERNAL_WORKER_AUDIENCE", "https://worker.test")
    monkeypatch.setenv("PHARMAIDE_TASK_BACKEND", "cloud_tasks")
    monkeypatch.setenv(
        "PHARMAIDE_CLOUD_TASKS_QUEUE_PATH",
        "projects/pharmaide/locations/europe-west2/queues/analysis",
    )
    monkeypatch.setenv("PHARMAIDE_CLOUD_TASKS_BASE_URL", "https://worker.test")
    monkeypatch.setenv(
        "PHARMAIDE_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL",
        "tasks-invoker@pharmaide.iam.gserviceaccount.com",
    )
    monkeypatch.setenv("PHARMAIDE_CLOUD_TASKS_OIDC_AUDIENCE", "https://worker.test")

    settings = Settings(_env_file=None)

    assert settings.log_mode == "json"
    assert settings.debug_routes_enabled is True
    assert settings.cors_allowed_origin_list == (
        "https://app.example",
        "https://admin.example",
    )
    assert settings.auth_mode == "gcip"
    assert settings.gcip_project_id == "pharmaide-staging"
    assert settings.checkpoint_db_path == "/tmp/x.db"
    assert settings.rxnorm_base_url == "https://rxnav.test/REST"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-test"
    assert settings.whatsapp_webhook_verify_token is not None
    assert settings.whatsapp_webhook_verify_token.get_secret_value() == "verify-me"
    assert settings.whatsapp_webhook_app_secret is not None
    assert settings.whatsapp_webhook_app_secret.get_secret_value() == "app-secret"
    assert settings.whatsapp_delivery_provider == "cloud_api"
    assert settings.whatsapp_cloud_api_access_token is not None
    assert settings.whatsapp_cloud_api_access_token.get_secret_value() == "wa-token"
    assert settings.whatsapp_cloud_api_phone_number_id == "phone-number-id"
    assert settings.whatsapp_cloud_api_version == "v24.0"
    assert settings.whatsapp_cloud_api_base_url == "https://graph.test"
    assert settings.safety_provider == "remote_http"
    assert settings.llama_guard_url == "https://safety.test/v1/guard/check"
    assert settings.agentdog_url == "https://safety.test/v1/referee/review"
    assert settings.safety_provider_api_key is not None
    assert settings.safety_provider_api_key.get_secret_value() == "safety-test"
    assert settings.safety_provider_timeout_seconds == 8
    assert settings.analysis_timeout_seconds == 12
    assert settings.max_concurrent_analyses_per_user == 5
    assert settings.knowledge_upload_dir == "/tmp/kb"
    assert settings.knowledge_max_upload_bytes == 1024
    assert settings.knowledge_ingestion_stale_minutes == 7
    assert settings.internal_worker_auth == "oidc"
    assert settings.internal_worker_audience == "https://worker.test"
    assert settings.task_backend == "cloud_tasks"
    assert (
        settings.cloud_tasks_queue_path
        == "projects/pharmaide/locations/europe-west2/queues/analysis"
    )
    assert settings.cloud_tasks_base_url == "https://worker.test"
    assert (
        settings.cloud_tasks_service_account_email
        == "tasks-invoker@pharmaide.iam.gserviceaccount.com"
    )
    assert settings.cloud_tasks_oidc_audience == "https://worker.test"


def test_settings_accepts_human_readable_knowledge_upload_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMAIDE_KNOWLEDGE_MAX_UPLOAD_BYTES", "25MB")

    settings = Settings(_env_file=None)

    assert settings.knowledge_max_upload_bytes == 25 * 1024 * 1024


def test_settings_rejects_unknown_safety_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMAIDE_SAFETY_PROVIDER", "llama_guard")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_requires_remote_http_safety_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMAIDE_SAFETY_PROVIDER", "remote_http")
    monkeypatch.delenv("PHARMAIDE_LLAMA_GUARD_URL", raising=False)
    monkeypatch.delenv("PHARMAIDE_AGENTDOG_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_requires_cloud_tasks_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMAIDE_TASK_BACKEND", "cloud_tasks")
    monkeypatch.delenv("PHARMAIDE_CLOUD_TASKS_QUEUE_PATH", raising=False)
    monkeypatch.delenv("PHARMAIDE_CLOUD_TASKS_BASE_URL", raising=False)
    monkeypatch.delenv("PHARMAIDE_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL", raising=False)
    monkeypatch.delenv("PHARMAIDE_CLOUD_TASKS_OIDC_AUDIENCE", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_requires_cloud_api_delivery_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_DELIVERY_PROVIDER", "cloud_api")
    monkeypatch.delenv("PHARMAIDE_WHATSAPP_CLOUD_API_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("PHARMAIDE_WHATSAPP_CLOUD_API_PHONE_NUMBER_ID", raising=False)
    monkeypatch.delenv("PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN", raising=False)
    monkeypatch.delenv("PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_requires_signed_webhook_for_cloud_api_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_DELIVERY_PROVIDER", "cloud_api")
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_CLOUD_API_ACCESS_TOKEN", "wa-token")
    monkeypatch.setenv("PHARMAIDE_WHATSAPP_CLOUD_API_PHONE_NUMBER_ID", "phone-number-id")
    monkeypatch.delenv("PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN", raising=False)
    monkeypatch.delenv("PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_requires_oidc_internal_worker_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHARMAIDE_INTERNAL_WORKER_AUTH", "oidc")
    monkeypatch.delenv("PHARMAIDE_INTERNAL_WORKER_AUDIENCE", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_requires_gcip_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMAIDE_AUTH_MODE", "gcip")
    monkeypatch.delenv("PHARMAIDE_GCIP_PROJECT_ID", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

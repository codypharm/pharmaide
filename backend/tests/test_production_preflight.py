"""Production deployment preflight checks."""

from uuid import UUID

from pydantic import SecretStr

from app.config import Settings
from app.services.production_preflight import run_production_preflight


def test_production_preflight_passes_for_production_shaped_settings() -> None:
    settings = _production_settings()

    report = run_production_preflight(settings)

    assert report.ok is True
    assert report.as_dict()["errors"] == []


def test_production_preflight_blocks_local_defaults() -> None:
    settings = Settings(_env_file=None)

    report = run_production_preflight(settings)

    assert report.ok is False
    codes = _error_codes(report.as_dict())
    assert "auth_mode" in codes
    assert "openai_api_key" in codes
    assert "whatsapp_provider" in codes
    assert "knowledge_storage" in codes
    assert "internal_worker_auth" in codes
    assert "task_backend" in codes
    assert "safety_provider" in codes


def test_production_preflight_warns_when_retention_cleanup_is_still_dry_run() -> None:
    settings = _production_settings(
        data_retention_cleanup_dry_run=True,
        audit_retention_cleanup_dry_run=True,
    )

    report = run_production_preflight(settings)

    assert report.ok is True
    warning_codes = {warning["code"] for warning in report.as_dict()["warnings"]}
    assert warning_codes == {"data_retention_dry_run", "audit_retention_dry_run"}


def test_production_preflight_rejects_non_https_runtime_urls() -> None:
    settings = _production_settings(
        cors_allowed_origins="http://app.example",
        cloud_tasks_base_url="http://api.example",
        cloud_tasks_oidc_audience="http://api.example",
    )

    report = run_production_preflight(settings)

    assert report.ok is False
    assert {"cors_https_only", "cloud_tasks_base_url", "cloud_tasks_oidc_audience"}.issubset(
        _error_codes(report.as_dict())
    )


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "auth_mode": "gcip",
        "gcip_project_id": "pharmaide-prod",
        "gcip_require_workspace_claim": True,
        "gcip_require_workspace_membership": True,
        "debug_routes_enabled": False,
        "log_mode": "json",
        "cors_allowed_origins": "https://app.pharmaide.example",
        "openai_api_key": SecretStr("sk-test"),
        "whatsapp_delivery_provider": "cloud_api",
        "whatsapp_cloud_api_access_token": SecretStr("wa-token"),
        "whatsapp_cloud_api_phone_number_id": "phone-number-id",
        "whatsapp_webhook_verify_token": SecretStr("verify-token"),
        "whatsapp_webhook_app_secret": SecretStr("app-secret"),
        "whatsapp_workspace_scope_id": UUID("11111111-1111-4111-8111-111111111111"),
        "knowledge_storage_backend": "gcs",
        "knowledge_gcs_bucket": "pharmaide-kb-prod",
        "internal_worker_auth": "oidc",
        "internal_worker_audience": "https://api.pharmaide.example",
        "task_backend": "cloud_tasks",
        "cloud_tasks_queue_path": "projects/pharmaide/locations/europe-west2/queues/default",
        "cloud_tasks_base_url": "https://api.pharmaide.example",
        "cloud_tasks_service_account_email": "tasks@pharmaide.iam.gserviceaccount.com",
        "cloud_tasks_oidc_audience": "https://api.pharmaide.example",
        "safety_provider": "remote_http",
        "llama_guard_url": "https://safety.pharmaide.example/guard",
        "agentdog_url": "https://safety.pharmaide.example/referee",
        "data_retention_cleanup_dry_run": False,
        "audit_retention_cleanup_dry_run": False,
    }
    values.update(overrides)
    return Settings(**values)


def _error_codes(report: dict[str, object]) -> set[str]:
    return {error["code"] for error in report["errors"]}

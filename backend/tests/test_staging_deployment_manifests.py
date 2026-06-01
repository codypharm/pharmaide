"""Staging deployment manifest files stay validator-compatible."""

import json
from pathlib import Path
from uuid import UUID

from app.config import Settings
from app.services.cloud_tasks_scheduler_manifest import (
    validate_cloud_tasks_scheduler_manifest,
)
from app.services.deployment_manifest import validate_deployment_manifest
from app.services.gcip_claims_manifest import validate_gcip_claims_manifest
from app.services.knowledge_storage_manifest import validate_knowledge_storage_manifest
from app.services.retention_approval_manifest import validate_retention_approval_manifest
from app.services.safety_gateway_manifest import validate_safety_gateway_manifest
from app.services.whatsapp_workspace_manifest import validate_whatsapp_workspace_manifest

MANIFEST_DIR = Path(__file__).resolve().parents[2] / "docs/deployment-manifests/staging"
WORKSPACE_ID = UUID("11111111-1111-4111-8111-111111111111")
BACKEND_URL = "https://api.staging.pharmaide.example"
FRONTEND_URL = "https://app.staging.pharmaide.example"


def test_staging_deployment_manifests_validate_against_staging_settings() -> None:
    settings = _staging_settings()

    reports = [
        validate_gcip_claims_manifest(_manifest("claims-manifest.json"), settings),
        validate_whatsapp_workspace_manifest(_manifest("whatsapp-manifest.json"), settings),
        validate_knowledge_storage_manifest(
            _manifest("knowledge-storage-manifest.json"),
            settings,
        ),
        validate_cloud_tasks_scheduler_manifest(
            _manifest("cloud-tasks-manifest.json"),
            settings,
        ),
        validate_safety_gateway_manifest(_manifest("safety-gateway-manifest.json"), settings),
        validate_retention_approval_manifest(_manifest("retention-manifest.json"), settings),
        validate_deployment_manifest(_manifest("deployment-manifest.json"), settings),
    ]

    assert all(report.ok for report in reports), [report.as_dict() for report in reports]


def _manifest(name: str) -> dict[str, object]:
    return json.loads((MANIFEST_DIR / name).read_text())


def _staging_settings() -> Settings:
    return Settings(
        _env_file=None,
        cors_allowed_origins=FRONTEND_URL,
        whatsapp_cloud_api_phone_number_id="1234567890",
        whatsapp_workspace_scope_id=WORKSPACE_ID,
        knowledge_storage_backend="gcs",
        knowledge_gcs_bucket="pharmaide-staging-kb",
        knowledge_gcs_prefix="kb_uploads",
        knowledge_max_upload_bytes=25 * 1024 * 1024,
        data_retention_closed_treatment_days=365,
        audit_retention_operational_days=365,
        internal_worker_auth="oidc",
        internal_worker_audience=BACKEND_URL,
        task_backend="cloud_tasks",
        cloud_tasks_queue_path="projects/pharmaide-staging/locations/europe-west2/queues/internal",
        cloud_tasks_base_url=BACKEND_URL,
        cloud_tasks_service_account_email=(
            "tasks-invoker@pharmaide-staging.iam.gserviceaccount.com"
        ),
        cloud_tasks_oidc_audience=BACKEND_URL,
        safety_provider="remote_http",
        llama_guard_url=(
            "https://llama-guard.internal.staging.pharmaide.example/v1/guard/check"
        ),
        agentdog_url="https://agentdog.internal.staging.pharmaide.example/v1/referee/review",
        safety_provider_timeout_seconds=10,
    )

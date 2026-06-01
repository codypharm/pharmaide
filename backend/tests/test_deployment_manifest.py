"""Cloud Run deployment manifest validation."""

import json
import os
import subprocess
import sys
from pathlib import Path

from app.config import Settings
from app.services.deployment_manifest import validate_deployment_manifest


def test_deployment_manifest_accepts_valid_runtime_manifest() -> None:
    report = validate_deployment_manifest(_valid_manifest(), _deployment_settings())

    assert report.ok is True
    assert report.environment == "staging"
    assert report.backend_url == "https://api.staging.pharmaide.example"
    assert report.frontend_url == "https://app.staging.pharmaide.example"
    assert report.as_dict()["errors"] == []


def test_deployment_manifest_rejects_mutable_images_and_missing_artifact_policy() -> None:
    manifest = _valid_manifest()
    manifest["backend"]["image"] = "us-docker.pkg.dev/pharmaide/backend:latest"
    manifest["artifact_policy"]["image_signing_required"] = False

    report = validate_deployment_manifest(manifest, _deployment_settings())

    assert report.ok is False
    assert {
        "backend_image_digest_required",
        "image_signing_required",
    }.issubset({error.code for error in report.errors})


def test_deployment_manifest_rejects_insecure_urls_and_runtime_mismatch() -> None:
    manifest = _valid_manifest()
    manifest["backend"]["url"] = "http://api.staging.pharmaide.example"
    manifest["frontend"]["url"] = "http://app.staging.pharmaide.example"

    report = validate_deployment_manifest(manifest, _deployment_settings())

    assert report.ok is False
    assert {
        "backend_url_invalid",
        "frontend_url_invalid",
        "backend_url_mismatch",
        "frontend_origin_missing_from_cors",
    }.issubset({error.code for error in report.errors})


def test_deployment_manifest_rejects_missing_required_secret_bindings() -> None:
    manifest = _valid_manifest()
    del manifest["backend"]["secret_env"]["PHARMAIDE_OPENAI_API_KEY"]

    report = validate_deployment_manifest(manifest, _deployment_settings())

    assert report.ok is False
    assert "backend_secret_missing" in {error.code for error in report.errors}


def test_deployment_manifest_rejects_secret_values_instead_of_secret_refs() -> None:
    manifest = _valid_manifest()
    manifest["backend"]["secret_env"]["PHARMAIDE_DATABASE_URL"] = "postgresql://secret"

    report = validate_deployment_manifest(manifest, _deployment_settings())

    assert report.ok is False
    assert "backend_secret_ref_invalid" in {error.code for error in report.errors}


def test_deployment_manifest_cli_outputs_valid_report(tmp_path: Path) -> None:
    manifest_path = tmp_path / "deployment.json"
    manifest_path.write_text(json.dumps(_valid_manifest()))

    result = subprocess.run(
        [sys.executable, "scripts/deployment_manifest.py", str(manifest_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PHARMAIDE_CORS_ALLOWED_ORIGINS": "https://app.staging.pharmaide.example",
            "PHARMAIDE_INTERNAL_WORKER_AUTH": "oidc",
            "PHARMAIDE_INTERNAL_WORKER_AUDIENCE": "https://api.staging.pharmaide.example",
            "PHARMAIDE_TASK_BACKEND": "cloud_tasks",
            "PHARMAIDE_CLOUD_TASKS_QUEUE_PATH": (
                "projects/pharmaide-staging/locations/europe-west2/queues/internal"
            ),
            "PHARMAIDE_CLOUD_TASKS_BASE_URL": "https://api.staging.pharmaide.example",
            "PHARMAIDE_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL": (
                "tasks-invoker@pharmaide-staging.iam.gserviceaccount.com"
            ),
            "PHARMAIDE_CLOUD_TASKS_OIDC_AUDIENCE": "https://api.staging.pharmaide.example",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["backend_url"] == "https://api.staging.pharmaide.example"


def _deployment_settings() -> Settings:
    return Settings(
        _env_file=None,
        cors_allowed_origins="https://app.staging.pharmaide.example",
        internal_worker_auth="oidc",
        internal_worker_audience="https://api.staging.pharmaide.example",
        task_backend="cloud_tasks",
        cloud_tasks_queue_path="projects/pharmaide-staging/locations/europe-west2/queues/internal",
        cloud_tasks_base_url="https://api.staging.pharmaide.example",
        cloud_tasks_service_account_email=(
            "tasks-invoker@pharmaide-staging.iam.gserviceaccount.com"
        ),
        cloud_tasks_oidc_audience="https://api.staging.pharmaide.example",
    )


def _valid_manifest() -> dict[str, object]:
    return {
        "environment": "staging",
        "project_id": "pharmaide-staging",
        "region": "europe-west2",
        "backend": {
            "service_name": "pharmaide-api",
            "image": (
                "europe-west2-docker.pkg.dev/pharmaide-staging/pharmaide/backend"
                "@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            ),
            "url": "https://api.staging.pharmaide.example",
            "runtime_service_account_email": (
                "backend-runtime@pharmaide-staging.iam.gserviceaccount.com"
            ),
            "min_instances": 0,
            "max_instances": 10,
            "secret_env": {
                "PHARMAIDE_DATABASE_URL": (
                    "projects/pharmaide-staging/secrets/pharmaide-database-url"
                ),
                "PHARMAIDE_OPENAI_API_KEY": (
                    "projects/pharmaide-staging/secrets/pharmaide-openai-api-key"
                ),
                "PHARMAIDE_WHATSAPP_CLOUD_API_ACCESS_TOKEN": (
                    "projects/pharmaide-staging/secrets/pharmaide-whatsapp-access-token"
                ),
                "PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN": (
                    "projects/pharmaide-staging/secrets/pharmaide-whatsapp-verify-token"
                ),
                "PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET": (
                    "projects/pharmaide-staging/secrets/pharmaide-whatsapp-app-secret"
                ),
            },
        },
        "frontend": {
            "service_name": "pharmaide-web",
            "image": (
                "europe-west2-docker.pkg.dev/pharmaide-staging/pharmaide/frontend"
                "@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            ),
            "url": "https://app.staging.pharmaide.example",
            "build_env": {
                "VITE_API_BASE_URL": "https://api.staging.pharmaide.example",
                "VITE_AUTH_MODE": "gcip",
                "VITE_GCIP_PROJECT_ID": "pharmaide-staging",
            },
        },
        "artifact_policy": {
            "image_scanning_required": True,
            "image_signing_required": True,
        },
    }

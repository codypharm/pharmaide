"""Cloud Tasks and scheduler deployment manifest validation."""

import json
import os
import subprocess
import sys
from pathlib import Path

from app.config import Settings
from app.services.cloud_tasks_scheduler_manifest import (
    validate_cloud_tasks_scheduler_manifest,
)


def test_cloud_tasks_scheduler_manifest_accepts_valid_runtime_manifest() -> None:
    settings = _cloud_tasks_settings()

    report = validate_cloud_tasks_scheduler_manifest(_valid_manifest(), settings)

    assert report.ok is True
    assert report.required_tick_count == 5
    assert report.as_dict()["errors"] == []


def test_cloud_tasks_scheduler_manifest_rejects_missing_and_duplicate_ticks() -> None:
    manifest = _valid_manifest()
    manifest["scheduler"]["ticks"] = [
        {"tick_type": "due_monitoring", "schedule": "*/5 * * * *"},
        {"tick_type": "due_monitoring", "schedule": "*/5 * * * *"},
    ]

    report = validate_cloud_tasks_scheduler_manifest(manifest, Settings(_env_file=None))

    assert report.ok is False
    assert {
        "duplicate_tick_type",
        "required_tick_missing",
    }.issubset({error.code for error in report.errors})


def test_cloud_tasks_scheduler_manifest_rejects_invalid_gcp_and_https_fields() -> None:
    manifest = _valid_manifest()
    manifest["cloud_tasks"]["queue_path"] = "queues/internal"
    manifest["cloud_tasks"]["base_url"] = "http://backend.example"
    manifest["cloud_tasks"]["service_account_email"] = "worker@example.com"
    manifest["scheduler"]["pubsub_topic"] = "topic"
    manifest["scheduler"]["push_endpoint"] = "http://backend.example/internal/scheduler/pubsub"
    manifest["scheduler"]["dead_letter_topic"] = "dead-letter"

    report = validate_cloud_tasks_scheduler_manifest(manifest, Settings(_env_file=None))

    assert report.ok is False
    assert {
        "cloud_tasks_queue_path_invalid",
        "cloud_tasks_base_url_invalid",
        "cloud_tasks_service_account_email_invalid",
        "scheduler_pubsub_topic_invalid",
        "scheduler_push_endpoint_invalid",
        "scheduler_dead_letter_topic_invalid",
    }.issubset({error.code for error in report.errors})


def test_cloud_tasks_scheduler_manifest_rejects_runtime_mismatch() -> None:
    manifest = _valid_manifest()
    manifest["cloud_tasks"]["queue_path"] = (
        "projects/pharmaide-prod/locations/us-central1/queues/other"
    )
    manifest["scheduler"]["push_oidc_audience"] = "https://wrong.example"

    report = validate_cloud_tasks_scheduler_manifest(manifest, _cloud_tasks_settings())

    assert report.ok is False
    assert {
        "cloud_tasks_queue_path_mismatch",
        "scheduler_push_oidc_audience_mismatch",
    }.issubset({error.code for error in report.errors})


def test_cloud_tasks_scheduler_manifest_requires_scheduler_ticks_list() -> None:
    report = validate_cloud_tasks_scheduler_manifest(
        {"cloud_tasks": _valid_manifest()["cloud_tasks"], "scheduler": {}},
        Settings(_env_file=None),
    )

    assert report.ok is False
    assert "scheduler_ticks_required" in {error.code for error in report.errors}


def test_cloud_tasks_scheduler_manifest_cli_outputs_valid_report(tmp_path: Path) -> None:
    manifest_path = tmp_path / "cloud-tasks.json"
    manifest_path.write_text(json.dumps(_valid_manifest()))

    result = subprocess.run(
        [sys.executable, "scripts/cloud_tasks_scheduler_manifest.py", str(manifest_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PHARMAIDE_INTERNAL_WORKER_AUTH": "oidc",
            "PHARMAIDE_INTERNAL_WORKER_AUDIENCE": "https://backend.example",
            "PHARMAIDE_TASK_BACKEND": "cloud_tasks",
            "PHARMAIDE_CLOUD_TASKS_QUEUE_PATH": (
                "projects/pharmaide-prod/locations/us-central1/queues/internal"
            ),
            "PHARMAIDE_CLOUD_TASKS_BASE_URL": "https://backend.example",
            "PHARMAIDE_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL": (
                "tasks-invoker@pharmaide-prod.iam.gserviceaccount.com"
            ),
            "PHARMAIDE_CLOUD_TASKS_OIDC_AUDIENCE": "https://backend.example",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["required_tick_count"] == 5


def _cloud_tasks_settings() -> Settings:
    return Settings(
        _env_file=None,
        internal_worker_auth="oidc",
        internal_worker_audience="https://backend.example",
        task_backend="cloud_tasks",
        cloud_tasks_queue_path="projects/pharmaide-prod/locations/us-central1/queues/internal",
        cloud_tasks_base_url="https://backend.example",
        cloud_tasks_service_account_email=(
            "tasks-invoker@pharmaide-prod.iam.gserviceaccount.com"
        ),
        cloud_tasks_oidc_audience="https://backend.example",
    )


def _valid_manifest() -> dict[str, object]:
    return {
        "cloud_tasks": {
            "queue_path": "projects/pharmaide-prod/locations/us-central1/queues/internal",
            "base_url": "https://backend.example",
            "service_account_email": "tasks-invoker@pharmaide-prod.iam.gserviceaccount.com",
            "oidc_audience": "https://backend.example",
        },
        "scheduler": {
            "pubsub_topic": "projects/pharmaide-prod/topics/internal-scheduler",
            "push_endpoint": "https://backend.example/internal/scheduler/pubsub",
            "push_service_account_email": (
                "tasks-invoker@pharmaide-prod.iam.gserviceaccount.com"
            ),
            "push_oidc_audience": "https://backend.example",
            "dead_letter_topic": "projects/pharmaide-prod/topics/internal-dead-letter",
            "ticks": [
                {"tick_type": "due_monitoring", "schedule": "*/5 * * * *"},
                {"tick_type": "message_delivery", "schedule": "*/2 * * * *"},
                {"tick_type": "closed_treatment_retention", "schedule": "0 2 * * *"},
                {"tick_type": "knowledge_upload_file_cleanup", "schedule": "0 3 * * *"},
                {"tick_type": "operational_audit_retention", "schedule": "0 4 * * *"},
            ],
        },
    }

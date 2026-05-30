"""Validate Cloud Tasks and Cloud Scheduler deployment manifests.

The application already has internal worker routes and scheduler tick handlers.
This module checks the operator-owned GCP wiring around those routes before a
deployment relies on durable background work. The manifest intentionally carries
only queue, topic, URL, and service-account metadata; clinical payloads stay in
the database and are loaded by id inside worker routes.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from app.config import Settings

REQUIRED_SCHEDULER_TICKS = frozenset(
    {
        "due_monitoring",
        "message_delivery",
        "closed_treatment_retention",
        "knowledge_upload_file_cleanup",
        "operational_audit_retention",
    }
)

_QUEUE_PATH_RE = re.compile(r"^projects/[^/]+/locations/[^/]+/queues/[^/]+$")
_TOPIC_PATH_RE = re.compile(r"^projects/[^/]+/topics/[^/]+$")
_SERVICE_ACCOUNT_RE = re.compile(r"^[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com$")


@dataclass(frozen=True)
class CloudTasksSchedulerManifestError:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class SchedulerTickProjection:
    tick_type: str
    schedule: str

    def as_dict(self) -> dict[str, str]:
        return {
            "tick_type": self.tick_type,
            "schedule": self.schedule,
        }


@dataclass(frozen=True)
class CloudTasksSchedulerManifestReport:
    required_tick_count: int
    configured_ticks: tuple[SchedulerTickProjection, ...]
    errors: tuple[CloudTasksSchedulerManifestError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "required_tick_count": self.required_tick_count,
            "configured_ticks": [tick.as_dict() for tick in self.configured_ticks],
            "errors": [error.as_dict() for error in self.errors],
        }


def validate_cloud_tasks_scheduler_manifest(
    manifest: Mapping[str, object],
    settings: Settings,
) -> CloudTasksSchedulerManifestReport:
    """Validate GCP worker queue and scheduler metadata against runtime settings."""
    errors: list[CloudTasksSchedulerManifestError] = []
    cloud_tasks = _mapping(manifest.get("cloud_tasks"))
    scheduler = _mapping(manifest.get("scheduler"))

    if cloud_tasks is None:
        errors.append(
            _error("cloud_tasks_required", "Manifest must contain a cloud_tasks object.")
        )
    else:
        _validate_cloud_tasks(cloud_tasks, settings, errors)

    ticks: tuple[SchedulerTickProjection, ...] = ()
    if scheduler is None:
        errors.append(_error("scheduler_required", "Manifest must contain a scheduler object."))
    else:
        ticks = _validate_scheduler(scheduler, settings, errors)

    return CloudTasksSchedulerManifestReport(
        required_tick_count=len(REQUIRED_SCHEDULER_TICKS),
        configured_ticks=ticks,
        errors=tuple(errors),
    )


def _validate_cloud_tasks(
    cloud_tasks: Mapping[str, object],
    settings: Settings,
    errors: list[CloudTasksSchedulerManifestError],
) -> None:
    queue_path = _required_text(cloud_tasks.get("queue_path"))
    base_url = _required_text(cloud_tasks.get("base_url"))
    service_account = _required_text(cloud_tasks.get("service_account_email"))
    oidc_audience = _required_text(cloud_tasks.get("oidc_audience"))

    _require_match(queue_path, _QUEUE_PATH_RE, errors, "cloud_tasks_queue_path_invalid")
    _require_https_url(base_url, errors, "cloud_tasks_base_url_invalid")
    _require_service_account(
        service_account,
        errors,
        "cloud_tasks_service_account_email_invalid",
    )
    _require_https_url(oidc_audience, errors, "cloud_tasks_oidc_audience_invalid")

    # If the app is configured for Cloud Tasks, the manifest must describe the
    # exact queue identity the deployed backend will enqueue into.
    if settings.task_backend == "cloud_tasks":
        _require_runtime_match(
            queue_path,
            settings.cloud_tasks_queue_path,
            errors,
            "cloud_tasks_queue_path_mismatch",
            "cloud_tasks.queue_path must match PHARMAIDE_CLOUD_TASKS_QUEUE_PATH.",
        )
        _require_runtime_match(
            base_url,
            settings.cloud_tasks_base_url,
            errors,
            "cloud_tasks_base_url_mismatch",
            "cloud_tasks.base_url must match PHARMAIDE_CLOUD_TASKS_BASE_URL.",
        )
        _require_runtime_match(
            service_account,
            settings.cloud_tasks_service_account_email,
            errors,
            "cloud_tasks_service_account_email_mismatch",
            (
                "cloud_tasks.service_account_email must match "
                "PHARMAIDE_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL."
            ),
        )
        _require_runtime_match(
            oidc_audience,
            settings.cloud_tasks_oidc_audience,
            errors,
            "cloud_tasks_oidc_audience_mismatch",
            "cloud_tasks.oidc_audience must match PHARMAIDE_CLOUD_TASKS_OIDC_AUDIENCE.",
        )


def _validate_scheduler(
    scheduler: Mapping[str, object],
    settings: Settings,
    errors: list[CloudTasksSchedulerManifestError],
) -> tuple[SchedulerTickProjection, ...]:
    pubsub_topic = _required_text(scheduler.get("pubsub_topic"))
    push_endpoint = _required_text(scheduler.get("push_endpoint"))
    push_service_account = _required_text(scheduler.get("push_service_account_email"))
    push_oidc_audience = _required_text(scheduler.get("push_oidc_audience"))
    dead_letter_topic = _required_text(scheduler.get("dead_letter_topic"))

    _require_match(pubsub_topic, _TOPIC_PATH_RE, errors, "scheduler_pubsub_topic_invalid")
    _require_https_url(push_endpoint, errors, "scheduler_push_endpoint_invalid")
    _require_service_account(
        push_service_account,
        errors,
        "scheduler_push_service_account_email_invalid",
    )
    _require_https_url(push_oidc_audience, errors, "scheduler_push_oidc_audience_invalid")
    _require_match(
        dead_letter_topic,
        _TOPIC_PATH_RE,
        errors,
        "scheduler_dead_letter_topic_invalid",
    )

    if settings.internal_worker_auth == "oidc":
        _require_runtime_match(
            push_oidc_audience,
            settings.internal_worker_audience,
            errors,
            "scheduler_push_oidc_audience_mismatch",
            (
                "scheduler.push_oidc_audience must match "
                "PHARMAIDE_INTERNAL_WORKER_AUDIENCE."
            ),
        )

    return _validate_scheduler_ticks(scheduler.get("ticks"), errors)


def _validate_scheduler_ticks(
    value: object,
    errors: list[CloudTasksSchedulerManifestError],
) -> tuple[SchedulerTickProjection, ...]:
    if not isinstance(value, list):
        errors.append(
            _error("scheduler_ticks_required", "scheduler.ticks must be a list.")
        )
        return ()

    ticks: list[SchedulerTickProjection] = []
    seen_tick_types: set[str] = set()
    for raw_tick in value:
        if not isinstance(raw_tick, Mapping):
            errors.append(_error("scheduler_tick_object_required", "Each tick must be an object."))
            continue

        tick_type = _required_text(raw_tick.get("tick_type"))
        schedule = _required_text(raw_tick.get("schedule"))
        if tick_type is None:
            errors.append(_error("scheduler_tick_type_required", "tick_type is required."))
            continue
        if tick_type in seen_tick_types:
            errors.append(
                _error("duplicate_tick_type", f"Scheduler tick {tick_type} appears twice.")
            )
            continue
        seen_tick_types.add(tick_type)

        if schedule is None or not _cron_schedule(schedule):
            errors.append(
                _error(
                    "scheduler_tick_schedule_invalid",
                    f"Scheduler tick {tick_type} must use a five-field cron schedule.",
                )
            )
            continue
        ticks.append(SchedulerTickProjection(tick_type=tick_type, schedule=schedule))

    missing_ticks = REQUIRED_SCHEDULER_TICKS - seen_tick_types
    for tick_type in sorted(missing_ticks):
        errors.append(
            _error("required_tick_missing", f"Required scheduler tick missing: {tick_type}.")
        )
    return tuple(ticks)


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _required_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _require_match(
    value: str | None,
    pattern: re.Pattern[str],
    errors: list[CloudTasksSchedulerManifestError],
    code: str,
) -> None:
    if value is None or pattern.fullmatch(value) is None:
        errors.append(_error(code, f"{code.removesuffix('_invalid')} is malformed."))


def _require_https_url(
    value: str | None,
    errors: list[CloudTasksSchedulerManifestError],
    code: str,
) -> None:
    parsed = urlparse(value or "")
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append(_error(code, f"{code.removesuffix('_invalid')} must be an HTTPS URL."))


def _require_service_account(
    value: str | None,
    errors: list[CloudTasksSchedulerManifestError],
    code: str,
) -> None:
    if value is None or _SERVICE_ACCOUNT_RE.fullmatch(value) is None:
        errors.append(
            _error(
                code,
                f"{code.removesuffix('_invalid')} must be a Google service account email.",
            )
        )


def _require_runtime_match(
    manifest_value: str | None,
    setting_value: str | None,
    errors: list[CloudTasksSchedulerManifestError],
    code: str,
    message: str,
) -> None:
    if manifest_value is not None and setting_value is not None and manifest_value != setting_value:
        errors.append(_error(code, message))


def _cron_schedule(value: str) -> bool:
    return len(value.split()) == 5


def _error(code: str, message: str) -> CloudTasksSchedulerManifestError:
    return CloudTasksSchedulerManifestError(code=code, message=message)


def manifest_json_example() -> str:
    """Return an operator-friendly example manifest."""
    return json.dumps(
        {
            "cloud_tasks": {
                "queue_path": "projects/pharmaide-prod/locations/us-central1/queues/internal",
                "base_url": "https://backend.example",
                "service_account_email": (
                    "tasks-invoker@pharmaide-prod.iam.gserviceaccount.com"
                ),
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
                    {
                        "tick_type": "knowledge_upload_file_cleanup",
                        "schedule": "0 3 * * *",
                    },
                    {"tick_type": "operational_audit_retention", "schedule": "0 4 * * *"},
                ],
            },
        },
        indent=2,
    )

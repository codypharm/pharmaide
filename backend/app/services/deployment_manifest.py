"""Validate Cloud Run deployment manifests.

This preflight checks the deployment plan before any cloud changes are applied.
It complements production settings preflight and post-deploy smoke tests by
catching mutable images, raw secret values, URL mismatches, and weak artifact
policy while the rollout is still just metadata.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from app.config import Settings

ALLOWED_ENVIRONMENTS = frozenset({"staging", "production"})
REQUIRED_BACKEND_SECRETS = frozenset(
    {
        "PHARMAIDE_DATABASE_URL",
        "PHARMAIDE_OPENAI_API_KEY",
        "PHARMAIDE_WHATSAPP_CLOUD_API_ACCESS_TOKEN",
        "PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN",
        "PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET",
    }
)

_GCP_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,62}$")
_REGION_RE = re.compile(r"^[a-z]+-[a-z]+[0-9]$")
_SERVICE_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_SERVICE_ACCOUNT_RE = re.compile(r"^[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com$")
_IMAGE_DIGEST_RE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
_SECRET_REF_RE = re.compile(r"^projects/[^/]+/secrets/[^/]+(?:/versions/[^/]+)?$")


@dataclass(frozen=True)
class DeploymentManifestError:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class DeploymentManifestReport:
    environment: str | None
    project_id: str | None
    region: str | None
    backend_url: str | None
    frontend_url: str | None
    errors: tuple[DeploymentManifestError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "environment": self.environment,
            "project_id": self.project_id,
            "region": self.region,
            "backend_url": self.backend_url,
            "frontend_url": self.frontend_url,
            "errors": [error.as_dict() for error in self.errors],
        }


def validate_deployment_manifest(
    manifest: Mapping[str, object],
    settings: Settings,
) -> DeploymentManifestReport:
    """Validate Cloud Run rollout metadata against runtime settings."""
    errors: list[DeploymentManifestError] = []
    environment = _text(manifest.get("environment"))
    project_id = _text(manifest.get("project_id"))
    region = _text(manifest.get("region"))
    backend = _mapping(manifest.get("backend"))
    frontend = _mapping(manifest.get("frontend"))
    artifact_policy = _mapping(manifest.get("artifact_policy"))

    backend_url = _text(backend.get("url")) if backend is not None else None
    frontend_url = _text(frontend.get("url")) if frontend is not None else None

    _validate_top_level(environment, project_id, region, errors)
    _validate_backend(backend, backend_url, settings, errors)
    _validate_frontend(frontend, frontend_url, backend_url, settings, errors)
    _validate_artifact_policy(artifact_policy, errors)

    return DeploymentManifestReport(
        environment=environment,
        project_id=project_id,
        region=region,
        backend_url=backend_url,
        frontend_url=frontend_url,
        errors=tuple(errors),
    )


def _validate_top_level(
    environment: str | None,
    project_id: str | None,
    region: str | None,
    errors: list[DeploymentManifestError],
) -> None:
    if environment not in ALLOWED_ENVIRONMENTS:
        errors.append(_error("environment_invalid", "environment must be staging or production."))
    if project_id is None or _GCP_ID_RE.fullmatch(project_id) is None:
        errors.append(_error("project_id_invalid", "project_id must be a valid GCP project id."))
    if region is None or _REGION_RE.fullmatch(region) is None:
        errors.append(_error("region_invalid", "region must be a valid GCP region id."))


def _validate_backend(
    backend: Mapping[str, object] | None,
    backend_url: str | None,
    settings: Settings,
    errors: list[DeploymentManifestError],
) -> None:
    if backend is None:
        errors.append(_error("backend_required", "backend object is required."))
        return

    _validate_service_name(backend.get("service_name"), "backend", errors)
    _validate_image(backend.get("image"), "backend", errors)
    _validate_https_url(backend_url, "backend", errors)
    _validate_service_account(backend.get("runtime_service_account_email"), "backend", errors)
    _validate_instance_bounds(backend, "backend", errors)
    _validate_backend_secrets(backend.get("secret_env"), errors)

    _require_match(
        backend_url,
        settings.cloud_tasks_base_url,
        errors,
        "backend_url_mismatch",
        "backend.url must match PHARMAIDE_CLOUD_TASKS_BASE_URL.",
    )
    _require_match(
        backend_url,
        settings.internal_worker_audience,
        errors,
        "backend_worker_audience_mismatch",
        "backend.url must match PHARMAIDE_INTERNAL_WORKER_AUDIENCE.",
    )


def _validate_frontend(
    frontend: Mapping[str, object] | None,
    frontend_url: str | None,
    backend_url: str | None,
    settings: Settings,
    errors: list[DeploymentManifestError],
) -> None:
    if frontend is None:
        errors.append(_error("frontend_required", "frontend object is required."))
        return

    _validate_service_name(frontend.get("service_name"), "frontend", errors)
    _validate_image(frontend.get("image"), "frontend", errors)
    _validate_https_url(frontend_url, "frontend", errors)
    _validate_frontend_build_env(frontend.get("build_env"), backend_url, errors)

    if frontend_url not in settings.cors_allowed_origin_list:
        errors.append(
            _error(
                "frontend_origin_missing_from_cors",
                "frontend.url must be included in PHARMAIDE_CORS_ALLOWED_ORIGINS.",
            )
        )


def _validate_artifact_policy(
    policy: Mapping[str, object] | None,
    errors: list[DeploymentManifestError],
) -> None:
    if policy is None:
        errors.append(_error("artifact_policy_required", "artifact_policy object is required."))
        return
    if policy.get("image_scanning_required") is not True:
        errors.append(
            _error(
                "image_scanning_required",
                "artifact_policy.image_scanning_required must be true.",
            )
        )
    if policy.get("image_signing_required") is not True:
        errors.append(
            _error("image_signing_required", "artifact_policy.image_signing_required must be true.")
        )


def _validate_service_name(
    value: object,
    label: str,
    errors: list[DeploymentManifestError],
) -> None:
    service_name = _text(value)
    if service_name is None or _SERVICE_RE.fullmatch(service_name) is None:
        errors.append(_error(f"{label}_service_name_invalid", f"{label}.service_name is invalid."))


def _validate_image(
    value: object,
    label: str,
    errors: list[DeploymentManifestError],
) -> None:
    image = _text(value)
    if image is None or _IMAGE_DIGEST_RE.fullmatch(image) is None:
        errors.append(
            _error(
                f"{label}_image_digest_required",
                f"{label}.image must be pinned to an immutable sha256 digest.",
            )
        )


def _validate_https_url(
    value: str | None,
    label: str,
    errors: list[DeploymentManifestError],
) -> None:
    parsed = urlparse(value or "")
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append(_error(f"{label}_url_invalid", f"{label}.url must be HTTPS."))


def _validate_service_account(
    value: object,
    label: str,
    errors: list[DeploymentManifestError],
) -> None:
    email = _text(value)
    if email is None or _SERVICE_ACCOUNT_RE.fullmatch(email) is None:
        errors.append(
            _error(
                f"{label}_runtime_service_account_invalid",
                f"{label}.runtime_service_account_email must be a Google service account.",
            )
        )


def _validate_instance_bounds(
    service: Mapping[str, object],
    label: str,
    errors: list[DeploymentManifestError],
) -> None:
    min_instances = _non_negative_int(service.get("min_instances"))
    max_instances = _positive_int(service.get("max_instances"))
    if min_instances is None:
        errors.append(
            _error(f"{label}_min_instances_invalid", f"{label}.min_instances is invalid.")
        )
    if max_instances is None:
        errors.append(
            _error(f"{label}_max_instances_invalid", f"{label}.max_instances is invalid.")
        )
    if min_instances is not None and max_instances is not None and min_instances > max_instances:
        errors.append(
            _error(
                f"{label}_instance_bounds_invalid",
                f"{label}.min_instances cannot exceed max_instances.",
            )
        )


def _validate_backend_secrets(
    value: object,
    errors: list[DeploymentManifestError],
) -> None:
    if not isinstance(value, Mapping):
        errors.append(
            _error("backend_secret_env_required", "backend.secret_env object is required.")
        )
        return

    secret_names = {key for key in value if isinstance(key, str)}
    for required_secret in sorted(REQUIRED_BACKEND_SECRETS - secret_names):
        errors.append(
            _error(
                "backend_secret_missing",
                f"backend.secret_env is missing {required_secret}.",
            )
        )

    for key, raw_ref in value.items():
        secret_ref = _text(raw_ref)
        if (
            not isinstance(key, str)
            or secret_ref is None
            or _SECRET_REF_RE.fullmatch(secret_ref) is None
        ):
            errors.append(
                _error(
                    "backend_secret_ref_invalid",
                    "backend.secret_env values must be Secret Manager resource refs.",
                )
            )


def _validate_frontend_build_env(
    value: object,
    backend_url: str | None,
    errors: list[DeploymentManifestError],
) -> None:
    if not isinstance(value, Mapping):
        errors.append(
            _error("frontend_build_env_required", "frontend.build_env object is required.")
        )
        return

    api_base_url = _text(value.get("VITE_API_BASE_URL"))
    auth_mode = _text(value.get("VITE_AUTH_MODE"))
    gcip_project_id = _text(value.get("VITE_GCIP_PROJECT_ID"))
    if api_base_url != backend_url:
        errors.append(
            _error(
                "frontend_api_base_url_mismatch",
                "frontend.build_env.VITE_API_BASE_URL must match backend.url.",
            )
        )
    if auth_mode != "gcip":
        errors.append(_error("frontend_auth_mode_invalid", "VITE_AUTH_MODE must be gcip."))
    if gcip_project_id is None:
        errors.append(
            _error("frontend_gcip_project_id_required", "VITE_GCIP_PROJECT_ID is required.")
        )

    # Frontend build args are browser-visible. They must not carry backend
    # PHARMAIDE_* secrets or raw token values.
    for key in value:
        if isinstance(key, str) and key.startswith("PHARMAIDE_"):
            errors.append(
                _error(
                    "frontend_secret_env_forbidden",
                    "frontend.build_env must not include backend PHARMAIDE_* values.",
                )
            )


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _require_match(
    manifest_value: str | None,
    setting_value: str | None,
    errors: list[DeploymentManifestError],
    code: str,
    message: str,
) -> None:
    if manifest_value is not None and setting_value is not None and manifest_value != setting_value:
        errors.append(_error(code, message))


def _error(code: str, message: str) -> DeploymentManifestError:
    return DeploymentManifestError(code=code, message=message)


def manifest_json_example() -> str:
    """Return an operator-friendly example manifest."""
    return json.dumps(
        {
            "environment": "staging",
            "project_id": "pharmaide-staging",
            "region": "europe-west2",
            "backend": {
                "service_name": "pharmaide-api",
                "image": "REGISTRY/backend@sha256:<64-hex-digest>",
                "url": "https://api.staging.pharmaide.example",
                "runtime_service_account_email": (
                    "backend-runtime@pharmaide-staging.iam.gserviceaccount.com"
                ),
                "min_instances": 0,
                "max_instances": 10,
                "secret_env": {
                    secret_name: f"projects/pharmaide-staging/secrets/{secret_name.lower()}"
                    for secret_name in sorted(REQUIRED_BACKEND_SECRETS)
                },
            },
            "frontend": {
                "service_name": "pharmaide-web",
                "image": "REGISTRY/frontend@sha256:<64-hex-digest>",
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
        },
        indent=2,
    )

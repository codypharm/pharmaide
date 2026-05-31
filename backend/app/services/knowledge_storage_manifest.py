"""Validate production knowledge-source storage manifests.

The smoke command proves the configured adapter can write/read/delete after
deployment. This manifest preflight catches unsafe or mismatched GCS settings
before operators provision the bucket or route clinic-uploaded source files to
durable object storage.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from app.config import Settings

MAX_APPROVED_UPLOAD_BYTES = 100 * 1024 * 1024

_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")
_PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_SERVICE_ACCOUNT_RE = re.compile(r"^[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com$")


@dataclass(frozen=True)
class KnowledgeStorageManifestError:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class KnowledgeStorageManifestReport:
    backend: str | None
    bucket_name: str | None
    prefix: str | None
    max_upload_bytes: int | None
    lifecycle_retention_days: int | None
    errors: tuple[KnowledgeStorageManifestError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "backend": self.backend,
            "bucket_name": self.bucket_name,
            "prefix": self.prefix,
            "max_upload_bytes": self.max_upload_bytes,
            "lifecycle_retention_days": self.lifecycle_retention_days,
            "errors": [error.as_dict() for error in self.errors],
        }


def validate_knowledge_storage_manifest(
    manifest: Mapping[str, object],
    settings: Settings,
) -> KnowledgeStorageManifestReport:
    """Validate GCS storage controls against the settings that will be deployed."""
    errors: list[KnowledgeStorageManifestError] = []
    storage = _mapping(manifest.get("storage"))
    gcs = _mapping(manifest.get("gcs"))

    backend: str | None = None
    bucket_name: str | None = None
    prefix: str | None = None
    max_upload_bytes: int | None = None
    lifecycle_days: int | None = None

    if storage is None:
        errors.append(_error("storage_required", "Manifest must contain a storage object."))
    else:
        backend = _text(storage.get("backend"))
        bucket_name = _text(storage.get("bucket_name"))
        prefix = _text(storage.get("prefix"))
        max_upload_bytes = _positive_int(storage.get("max_upload_bytes"))
        _validate_storage(storage, settings, errors)

    if gcs is None:
        errors.append(_error("gcs_required", "Manifest must contain a gcs object."))
    else:
        lifecycle_days = _positive_int(gcs.get("lifecycle_retention_days"))
        _validate_gcs(gcs, settings, errors)

    return KnowledgeStorageManifestReport(
        backend=backend,
        bucket_name=bucket_name,
        prefix=prefix,
        max_upload_bytes=max_upload_bytes,
        lifecycle_retention_days=lifecycle_days,
        errors=tuple(errors),
    )


def _validate_storage(
    storage: Mapping[str, object],
    settings: Settings,
    errors: list[KnowledgeStorageManifestError],
) -> None:
    backend = _text(storage.get("backend"))
    bucket_name = _text(storage.get("bucket_name"))
    prefix = _text(storage.get("prefix"))
    max_upload_bytes = _positive_int(storage.get("max_upload_bytes"))

    if backend != "gcs":
        errors.append(
            _error("backend_must_be_gcs", "Production knowledge storage must use gcs.")
        )
    if bucket_name is None or _BUCKET_RE.fullmatch(bucket_name) is None:
        errors.append(
            _error("bucket_name_invalid", "storage.bucket_name must be a valid GCS bucket name.")
        )
    if prefix is None or not _safe_prefix(prefix):
        errors.append(
            _error("prefix_invalid", "storage.prefix must be a safe object prefix.")
        )
    if max_upload_bytes is None or max_upload_bytes > MAX_APPROVED_UPLOAD_BYTES:
        errors.append(
            _error(
                "max_upload_bytes_invalid",
                f"storage.max_upload_bytes must be 1..{MAX_APPROVED_UPLOAD_BYTES}.",
            )
        )

    if settings.knowledge_storage_backend == "gcs":
        _require_match(
            bucket_name,
            settings.knowledge_gcs_bucket,
            errors,
            "bucket_name_mismatch",
            "storage.bucket_name must match PHARMAIDE_KNOWLEDGE_GCS_BUCKET.",
        )
        _require_match(
            prefix,
            settings.knowledge_gcs_prefix,
            errors,
            "prefix_mismatch",
            "storage.prefix must match PHARMAIDE_KNOWLEDGE_GCS_PREFIX.",
        )
        if (
            max_upload_bytes is not None
            and max_upload_bytes != settings.knowledge_max_upload_bytes
        ):
            errors.append(
                _error(
                    "max_upload_bytes_mismatch",
                    "storage.max_upload_bytes must match PHARMAIDE_KNOWLEDGE_MAX_UPLOAD_BYTES.",
                )
            )


def _validate_gcs(
    gcs: Mapping[str, object],
    settings: Settings,
    errors: list[KnowledgeStorageManifestError],
) -> None:
    service_account = _text(gcs.get("runtime_service_account_email"))
    lifecycle_days = _positive_int(gcs.get("lifecycle_retention_days"))

    if service_account is None or _SERVICE_ACCOUNT_RE.fullmatch(service_account) is None:
        errors.append(
            _error(
                "runtime_service_account_email_invalid",
                "gcs.runtime_service_account_email must be a Google service account email.",
            )
        )
    if lifecycle_days is None:
        errors.append(
            _error(
                "lifecycle_retention_days_invalid",
                "gcs.lifecycle_retention_days must be a positive integer.",
            )
        )
    elif lifecycle_days < settings.data_retention_closed_treatment_days:
        errors.append(
            _error(
                "lifecycle_retention_too_short",
                (
                    "gcs.lifecycle_retention_days must not delete uploaded source files "
                    "before closed treatment retention."
                ),
            )
        )

    # These controls prevent accidental public ACL drift for clinic-uploaded
    # source files even though object names themselves do not include PHI.
    if gcs.get("uniform_bucket_level_access") is not True:
        errors.append(
            _error(
                "uniform_bucket_level_access_required",
                "gcs.uniform_bucket_level_access must be true.",
            )
        )
    if gcs.get("public_access_prevention") != "enforced":
        errors.append(
            _error(
                "public_access_prevention_required",
                "gcs.public_access_prevention must be enforced.",
            )
        )


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _safe_prefix(value: str) -> bool:
    return (
        _PREFIX_RE.fullmatch(value) is not None
        and ".." not in value
        and not value.startswith("/")
        and not value.endswith("/")
    )


def _require_match(
    manifest_value: str | None,
    setting_value: str | None,
    errors: list[KnowledgeStorageManifestError],
    code: str,
    message: str,
) -> None:
    if manifest_value is not None and setting_value is not None and manifest_value != setting_value:
        errors.append(_error(code, message))


def _error(code: str, message: str) -> KnowledgeStorageManifestError:
    return KnowledgeStorageManifestError(code=code, message=message)


def manifest_json_example() -> str:
    """Return an operator-friendly example manifest."""
    return json.dumps(
        {
            "storage": {
                "backend": "gcs",
                "bucket_name": "pharmaide-kb-prod",
                "prefix": "kb_uploads",
                "max_upload_bytes": 25 * 1024 * 1024,
            },
            "gcs": {
                "runtime_service_account_email": (
                    "backend-runtime@pharmaide-prod.iam.gserviceaccount.com"
                ),
                "lifecycle_retention_days": 365,
                "uniform_bucket_level_access": True,
                "public_access_prevention": "enforced",
            },
        },
        indent=2,
    )

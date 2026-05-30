"""Validate production retention approval manifests.

Retention cleanup is already dry-run-first in code. This manifest records the
legal, clinical, and operations approval needed before production disables dry
run or applies object-storage lifecycle rules.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass

from app.config import Settings

MAX_RETENTION_DAYS = 3650


@dataclass(frozen=True)
class RetentionApprovalError:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class RetentionApprovalReport:
    closed_treatment_retention_days: int | None
    operational_audit_retention_days: int | None
    gcs_lifecycle_retention_days: int | None
    cleanup_apply_requested: bool
    errors: tuple[RetentionApprovalError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "closed_treatment_retention_days": self.closed_treatment_retention_days,
            "operational_audit_retention_days": self.operational_audit_retention_days,
            "gcs_lifecycle_retention_days": self.gcs_lifecycle_retention_days,
            "cleanup_apply_requested": self.cleanup_apply_requested,
            "errors": [error.as_dict() for error in self.errors],
        }


def validate_retention_approval_manifest(
    manifest: Mapping[str, object],
    settings: Settings,
) -> RetentionApprovalReport:
    """Validate retention approvals against the settings that will be deployed."""
    errors: list[RetentionApprovalError] = []
    closed_days = _retention_days(manifest.get("closed_treatment_retention_days"))
    operational_days = _retention_days(manifest.get("operational_audit_retention_days"))
    gcs_days = _retention_days(manifest.get("gcs_lifecycle_retention_days"))

    _require_days(errors, closed_days, "closed_treatment_retention_days")
    _require_days(errors, operational_days, "operational_audit_retention_days")
    _require_days(errors, gcs_days, "gcs_lifecycle_retention_days")
    _require_setting_match(
        errors,
        closed_days,
        settings.data_retention_closed_treatment_days,
        "closed_treatment_retention_days_mismatch",
        (
            "closed_treatment_retention_days must match "
            "PHARMAIDE_DATA_RETENTION_CLOSED_TREATMENT_DAYS."
        ),
    )
    _require_setting_match(
        errors,
        operational_days,
        settings.audit_retention_operational_days,
        "operational_audit_retention_days_mismatch",
        "operational_audit_retention_days must match PHARMAIDE_AUDIT_RETENTION_OPERATIONAL_DAYS.",
    )
    if closed_days is not None and gcs_days is not None and gcs_days < closed_days:
        errors.append(
            RetentionApprovalError(
                code="gcs_lifecycle_too_short",
                message=(
                    "gcs_lifecycle_retention_days must not delete uploaded source files "
                    "before closed treatment retention."
                ),
            )
        )

    if manifest.get("clinical_audit_logs_retained") is not True:
        errors.append(
            RetentionApprovalError(
                code="clinical_audit_logs_not_retained",
                message="clinical_audit_logs_retained must be true.",
            )
        )

    _validate_approvers(errors, manifest.get("approved_by"))
    cleanup_apply_requested = (
        not settings.data_retention_cleanup_dry_run
        or not settings.audit_retention_cleanup_dry_run
    )
    if cleanup_apply_requested and errors:
        errors.append(
            RetentionApprovalError(
                code="cleanup_apply_requires_valid_approval",
                message="Cleanup apply mode requires a valid retention approval manifest.",
            )
        )

    return RetentionApprovalReport(
        closed_treatment_retention_days=closed_days,
        operational_audit_retention_days=operational_days,
        gcs_lifecycle_retention_days=gcs_days,
        cleanup_apply_requested=cleanup_apply_requested,
        errors=tuple(errors),
    )


def _retention_days(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > MAX_RETENTION_DAYS:
        return None
    return value


def _require_days(
    errors: list[RetentionApprovalError],
    value: int | None,
    field: str,
) -> None:
    if value is None:
        errors.append(
            RetentionApprovalError(
                code=f"{field}_invalid",
                message=f"{field} must be an integer from 0 to {MAX_RETENTION_DAYS}.",
            )
        )


def _require_setting_match(
    errors: list[RetentionApprovalError],
    approved_value: int | None,
    setting_value: int,
    code: str,
    message: str,
) -> None:
    if approved_value is not None and approved_value != setting_value:
        errors.append(RetentionApprovalError(code=code, message=message))


def _validate_approvers(errors: list[RetentionApprovalError], value: object) -> None:
    if not isinstance(value, Mapping):
        errors.append(
            RetentionApprovalError(
                code="approvers_required",
                message="approved_by must contain clinical, legal, and operations approvers.",
            )
        )
        return

    for role in ("clinical", "legal", "operations"):
        approver = value.get(role)
        if not isinstance(approver, str) or not approver.strip():
            errors.append(
                RetentionApprovalError(
                    code=f"{role}_approver_required",
                    message=f"approved_by.{role} is required.",
                )
            )


def manifest_json_example() -> str:
    """Return an operator-friendly example manifest."""
    return json.dumps(
        {
            "closed_treatment_retention_days": 365,
            "operational_audit_retention_days": 365,
            "gcs_lifecycle_retention_days": 365,
            "clinical_audit_logs_retained": True,
            "approved_by": {
                "clinical": "Clinical Lead",
                "legal": "Legal Approver",
                "operations": "Operations Lead",
            },
        },
        indent=2,
    )

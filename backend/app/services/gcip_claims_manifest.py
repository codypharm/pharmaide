"""Validate GCIP custom-claims provisioning manifests.

This module does not call Google APIs. It gives operations a deterministic
preflight for pharmacist workspace claims before those claims are applied in
GCIP/Firebase.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from app.config import Settings

MAX_CUSTOM_CLAIMS_BYTES = 1000


@dataclass(frozen=True)
class ClaimsManifestError:
    index: int | None
    email: str | None
    code: str
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "email": self.email,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class ClaimsUserProjection:
    email: str
    custom_claims: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "email": self.email,
            "custom_claims": dict(self.custom_claims),
        }


@dataclass(frozen=True)
class ClaimsManifestReport:
    users: tuple[ClaimsUserProjection, ...]
    errors: tuple[ClaimsManifestError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "user_count": len(self.users),
            "users": [user.as_dict() for user in self.users],
            "errors": [error.as_dict() for error in self.errors],
        }


def validate_gcip_claims_manifest(
    manifest: Mapping[str, object],
    settings: Settings,
) -> ClaimsManifestReport:
    """Validate and project a GCIP claims manifest using configured claim names."""
    raw_users = manifest.get("users")
    if not isinstance(raw_users, list):
        return ClaimsManifestReport(
            users=(),
            errors=(
                ClaimsManifestError(
                    index=None,
                    email=None,
                    code="users_required",
                    message="Manifest must contain a users list.",
                ),
            ),
        )

    users: list[ClaimsUserProjection] = []
    errors: list[ClaimsManifestError] = []
    seen_emails: set[str] = set()
    for index, raw_user in enumerate(raw_users):
        if not isinstance(raw_user, Mapping):
            errors.append(
                _error(index, None, "user_object_required", "User entry must be an object.")
            )
            continue

        email = _email(raw_user.get("email"))
        if email is None:
            errors.append(_error(index, None, "email_required", "User email is required."))
            continue
        if email in seen_emails:
            errors.append(
                _error(index, email, "duplicate_email", "User email appears more than once.")
            )
            continue
        seen_emails.add(email)

        workspace_id = _uuid_text(raw_user.get("workspace_id"))
        if workspace_id is None:
            errors.append(
                _error(index, email, "workspace_id_required", "workspace_id must be a UUID.")
            )
            continue

        memberships = _workspace_memberships(raw_user.get("workspace_memberships"), workspace_id)
        if memberships is None:
            errors.append(
                _error(
                    index,
                    email,
                    "workspace_memberships_invalid",
                    "workspace_memberships must be omitted or a list of UUID strings.",
                )
            )
            continue
        if workspace_id not in memberships:
            errors.append(
                _error(
                    index,
                    email,
                    "workspace_membership_missing",
                    "workspace_memberships must include workspace_id.",
                )
            )
            continue

        claims = {
            settings.gcip_workspace_claim: workspace_id,
            settings.gcip_workspace_memberships_claim: memberships,
        }
        if _claim_size(claims) > MAX_CUSTOM_CLAIMS_BYTES:
            errors.append(
                _error(
                    index,
                    email,
                    "custom_claims_too_large",
                    "Custom claims exceed the GCIP/Firebase size limit.",
                )
            )
            continue

        users.append(ClaimsUserProjection(email=email, custom_claims=claims))

    return ClaimsManifestReport(users=tuple(users), errors=tuple(errors))


def _email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        return None
    return email


def _uuid_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value.strip()))
    except ValueError:
        return None


def _workspace_memberships(value: object, workspace_id: str) -> list[str] | None:
    if value is None:
        return [workspace_id]
    if not isinstance(value, Sequence) or isinstance(value, str):
        return None

    memberships: list[str] = []
    for raw_workspace_id in value:
        parsed = _uuid_text(raw_workspace_id)
        if parsed is None:
            return None
        if parsed not in memberships:
            memberships.append(parsed)
    return memberships


def _claim_size(claims: Mapping[str, object]) -> int:
    return len(json.dumps(claims, separators=(",", ":")).encode("utf-8"))


def _error(index: int, email: str | None, code: str, message: str) -> ClaimsManifestError:
    return ClaimsManifestError(index=index, email=email, code=code, message=message)

"""Validate WhatsApp phone-to-workspace rollout manifests.

The backend currently routes one configured WhatsApp sender number to one
workspace. This manifest preflight catches duplicate or malformed phone mappings
before operators apply production Meta/Cloud Run settings.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

import phonenumbers

from app.config import Settings


@dataclass(frozen=True)
class WhatsAppWorkspaceManifestError:
    index: int | None
    phone_number_id: str | None
    code: str
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "phone_number_id": self.phone_number_id,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class WhatsAppPhoneProjection:
    phone_number_id: str
    display_phone_number: str
    workspace_id: str
    matches_runtime_env: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "phone_number_id": self.phone_number_id,
            "display_phone_number": self.display_phone_number,
            "workspace_id": self.workspace_id,
            "matches_runtime_env": self.matches_runtime_env,
        }


@dataclass(frozen=True)
class WhatsAppWorkspaceManifestReport:
    phone_numbers: tuple[WhatsAppPhoneProjection, ...]
    errors: tuple[WhatsAppWorkspaceManifestError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "phone_number_count": len(self.phone_numbers),
            "phone_numbers": [phone.as_dict() for phone in self.phone_numbers],
            "errors": [error.as_dict() for error in self.errors],
        }


def validate_whatsapp_workspace_manifest(
    manifest: Mapping[str, object],
    settings: Settings,
) -> WhatsAppWorkspaceManifestReport:
    """Validate Meta phone number ownership and workspace routing metadata."""
    raw_phone_numbers = manifest.get("phone_numbers")
    if not isinstance(raw_phone_numbers, list):
        return WhatsAppWorkspaceManifestReport(
            phone_numbers=(),
            errors=(
                WhatsAppWorkspaceManifestError(
                    index=None,
                    phone_number_id=None,
                    code="phone_numbers_required",
                    message="Manifest must contain a phone_numbers list.",
                ),
            ),
        )

    phone_numbers: list[WhatsAppPhoneProjection] = []
    errors: list[WhatsAppWorkspaceManifestError] = []
    seen_phone_number_ids: set[str] = set()
    seen_display_numbers: set[str] = set()
    for index, raw_phone in enumerate(raw_phone_numbers):
        if not isinstance(raw_phone, Mapping):
            errors.append(
                _error(index, None, "phone_object_required", "Phone entry must be an object.")
            )
            continue

        phone_number_id = _required_text(raw_phone.get("phone_number_id"))
        if phone_number_id is None:
            errors.append(
                _error(index, None, "phone_number_id_required", "phone_number_id is required.")
            )
            continue
        if phone_number_id in seen_phone_number_ids:
            errors.append(
                _error(
                    index,
                    phone_number_id,
                    "duplicate_phone_number_id",
                    "phone_number_id appears more than once.",
                )
            )
            continue
        seen_phone_number_ids.add(phone_number_id)

        display_phone_number = _e164_phone(raw_phone.get("display_phone_number"))
        if display_phone_number is None:
            errors.append(
                _error(
                    index,
                    phone_number_id,
                    "display_phone_number_invalid",
                    "display_phone_number must be a valid E.164 phone number.",
                )
            )
            continue
        if display_phone_number in seen_display_numbers:
            errors.append(
                _error(
                    index,
                    phone_number_id,
                    "duplicate_display_phone_number",
                    "display_phone_number appears more than once.",
                )
            )
            continue
        seen_display_numbers.add(display_phone_number)

        workspace_id = _uuid_text(raw_phone.get("workspace_id"))
        if workspace_id is None:
            errors.append(
                _error(
                    index,
                    phone_number_id,
                    "workspace_id_required",
                    "workspace_id must be a UUID.",
                )
            )
            continue

        phone_numbers.append(
            WhatsAppPhoneProjection(
                phone_number_id=phone_number_id,
                display_phone_number=display_phone_number,
                workspace_id=workspace_id,
                matches_runtime_env=_matches_runtime_env(
                    phone_number_id,
                    workspace_id,
                    settings,
                ),
            )
        )

    _append_runtime_errors(phone_numbers, settings, errors)
    return WhatsAppWorkspaceManifestReport(
        phone_numbers=tuple(phone_numbers),
        errors=tuple(errors),
    )


def _append_runtime_errors(
    phone_numbers: list[WhatsAppPhoneProjection],
    settings: Settings,
    errors: list[WhatsAppWorkspaceManifestError],
) -> None:
    """Ensure configured staging env maps to exactly one manifest row when set."""
    configured_phone_number_id = settings.whatsapp_cloud_api_phone_number_id
    configured_workspace_id = settings.whatsapp_workspace_scope_id
    if configured_phone_number_id is None and configured_workspace_id is None:
        return

    matches = [phone for phone in phone_numbers if phone.matches_runtime_env]
    if len(matches) == 1:
        return

    errors.append(
        WhatsAppWorkspaceManifestError(
            index=None,
            phone_number_id=configured_phone_number_id,
            code="runtime_mapping_missing",
            message="Manifest must include exactly one row matching configured WhatsApp env.",
        )
    )


def _required_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _e164_phone(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = phonenumbers.parse(value.strip(), None)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def _uuid_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value.strip()))
    except ValueError:
        return None


def _matches_runtime_env(
    phone_number_id: str,
    workspace_id: str,
    settings: Settings,
) -> bool:
    return (
        settings.whatsapp_cloud_api_phone_number_id == phone_number_id
        and settings.whatsapp_workspace_scope_id is not None
        and str(settings.whatsapp_workspace_scope_id) == workspace_id
    )


def _error(
    index: int,
    phone_number_id: str | None,
    code: str,
    message: str,
) -> WhatsAppWorkspaceManifestError:
    return WhatsAppWorkspaceManifestError(
        index=index,
        phone_number_id=phone_number_id,
        code=code,
        message=message,
    )

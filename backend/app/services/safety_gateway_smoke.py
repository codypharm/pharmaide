"""Smoke check for the private safety gateway.

The probe uses synthetic, non-patient text and validates provider responses
with the same strict Pydantic schemas used by patient-facing safety orchestration.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.agents.remote_safety_providers import RemoteHttpGuardProvider, RemoteHttpRefereeProvider
from app.agents.safety_providers import (
    SafetyGuardProvider,
    SafetyProviderUnavailable,
    SafetyRefereeProvider,
)
from app.agents.safety_schemas import GuardRequest, GuardResult, RefereeRequest, RefereeResult
from app.config import Settings

SMOKE_TREATMENT_ID = UUID("00000000-0000-4000-8000-000000000001")


@dataclass(frozen=True)
class SafetyGatewaySmokeReport:
    ok: bool
    provider_mode: str
    guard_action: str | None
    referee_action: str | None
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "provider_mode": self.provider_mode,
            "guard_action": self.guard_action,
            "referee_action": self.referee_action,
            "errors": list(self.errors),
        }


async def run_safety_gateway_smoke(
    settings: Settings,
    *,
    guard_provider: SafetyGuardProvider | None = None,
    referee_provider: SafetyRefereeProvider | None = None,
) -> SafetyGatewaySmokeReport:
    """Call the configured private safety providers and validate both contracts."""
    if settings.safety_provider != "remote_http":
        return SafetyGatewaySmokeReport(
            ok=False,
            provider_mode=settings.safety_provider,
            guard_action=None,
            referee_action=None,
            errors=("safety_provider_must_be_remote_http",),
        )

    guard_provider = guard_provider or _build_guard_provider(settings)
    referee_provider = referee_provider or _build_referee_provider(settings)
    errors: list[str] = []
    guard_action: str | None = None
    referee_action: str | None = None

    try:
        guard_result = _validate_guard_payload(
            await guard_provider.check(_smoke_guard_request()),
            expected_stage="input",
        )
        guard_action = guard_result.action
    except Exception as exc:
        errors.append(_error_message("guard", exc))

    try:
        referee_result = _validate_referee_payload(
            await referee_provider.review(_smoke_referee_request())
        )
        referee_action = referee_result.action
    except Exception as exc:
        errors.append(_error_message("referee", exc))

    return SafetyGatewaySmokeReport(
        ok=not errors,
        provider_mode=settings.safety_provider,
        guard_action=guard_action,
        referee_action=referee_action,
        errors=tuple(errors),
    )


def _build_guard_provider(settings: Settings) -> RemoteHttpGuardProvider:
    if not settings.llama_guard_url:
        raise SafetyProviderUnavailable("llama_guard_url_missing")
    return RemoteHttpGuardProvider(
        url=settings.llama_guard_url,
        api_key=settings.safety_provider_api_key,
        timeout_seconds=settings.safety_provider_timeout_seconds,
    )


def _build_referee_provider(settings: Settings) -> RemoteHttpRefereeProvider:
    if not settings.agentdog_url:
        raise SafetyProviderUnavailable("agentdog_url_missing")
    return RemoteHttpRefereeProvider(
        url=settings.agentdog_url,
        api_key=settings.safety_provider_api_key,
        timeout_seconds=settings.safety_provider_timeout_seconds,
    )


def _smoke_guard_request() -> GuardRequest:
    return GuardRequest(
        stage="input",
        treatment_id=SMOKE_TREATMENT_ID,
        actor_role="patient",
        content="Can I take this medicine after food?",
    )


def _smoke_referee_request() -> RefereeRequest:
    return RefereeRequest(
        treatment_id=SMOKE_TREATMENT_ID,
        patient_message="Can I take this medicine after food?",
        assistant_draft="You can take it with food if that matches your pharmacist's instructions.",
        prescription_context="Synthetic test medication: one tablet once daily after food.",
    )


def _validate_guard_payload(
    payload: Mapping[str, Any],
    *,
    expected_stage: str,
) -> GuardResult:
    try:
        result = GuardResult.model_validate(payload)
    except ValidationError as exc:
        raise SafetyProviderUnavailable(f"guard_schema_invalid:{len(exc.errors())}") from exc
    if result.stage != expected_stage:
        raise SafetyProviderUnavailable("guard_stage_mismatch")
    return result


def _validate_referee_payload(payload: Mapping[str, Any]) -> RefereeResult:
    try:
        return RefereeResult.model_validate(payload)
    except ValidationError as exc:
        raise SafetyProviderUnavailable(f"referee_schema_invalid:{len(exc.errors())}") from exc


def _error_message(stage: str, exc: Exception) -> str:
    return f"{stage}:{exc.__class__.__name__}:{exc}"

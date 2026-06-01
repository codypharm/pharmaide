"""Validate private safety gateway deployment manifests.

The smoke command proves the live providers satisfy the strict Pydantic safety
schemas. This manifest preflight verifies the deployment boundary first:
remote mode, private HTTPS endpoints, restricted ingress, and runtime settings
that match the backend environment.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from app.config import Settings

ALLOWED_ENVIRONMENTS = frozenset({"staging", "production"})
ALLOWED_AUTH_MODES = frozenset({"bearer_token", "service_identity"})


@dataclass(frozen=True)
class SafetyGatewayManifestError:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class SafetyGatewayManifestReport:
    environment: str | None
    provider: str | None
    guard_url: str | None
    referee_url: str | None
    timeout_seconds: float | None
    errors: tuple[SafetyGatewayManifestError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "environment": self.environment,
            "provider": self.provider,
            "guard_url": self.guard_url,
            "referee_url": self.referee_url,
            "timeout_seconds": self.timeout_seconds,
            "errors": [error.as_dict() for error in self.errors],
        }


def validate_safety_gateway_manifest(
    manifest: Mapping[str, object],
    settings: Settings,
) -> SafetyGatewayManifestReport:
    """Validate private safety provider wiring against runtime settings."""
    errors: list[SafetyGatewayManifestError] = []
    environment = _text(manifest.get("environment"))
    provider = _text(manifest.get("provider"))
    guard = _mapping(manifest.get("guard"))
    referee = _mapping(manifest.get("referee"))
    auth = _mapping(manifest.get("auth"))
    network = _mapping(manifest.get("network"))
    timeout_seconds = _positive_number(manifest.get("timeout_seconds"))

    guard_url = _text(guard.get("url")) if guard is not None else None
    referee_url = _text(referee.get("url")) if referee is not None else None

    if environment not in ALLOWED_ENVIRONMENTS:
        errors.append(
            _error("environment_invalid", "environment must be staging or production.")
        )
    if provider != "remote_http":
        errors.append(
            _error("provider_must_be_remote_http", "provider must be remote_http.")
        )

    _validate_provider_endpoint("guard", guard, guard_url, settings.llama_guard_url, errors)
    _validate_provider_endpoint(
        "referee",
        referee,
        referee_url,
        settings.agentdog_url,
        errors,
    )
    _validate_auth(auth, errors)
    _validate_network(network, errors)
    _validate_timeout(timeout_seconds, settings, errors)

    if settings.safety_provider != "remote_http":
        errors.append(
            _error(
                "runtime_provider_mismatch",
                "PHARMAIDE_SAFETY_PROVIDER must be remote_http for this manifest.",
            )
        )

    return SafetyGatewayManifestReport(
        environment=environment,
        provider=provider,
        guard_url=guard_url,
        referee_url=referee_url,
        timeout_seconds=timeout_seconds,
        errors=tuple(errors),
    )


def _validate_provider_endpoint(
    label: str,
    provider: Mapping[str, object] | None,
    url: str | None,
    runtime_url: str | None,
    errors: list[SafetyGatewayManifestError],
) -> None:
    if provider is None:
        errors.append(_error(f"{label}_required", f"{label} provider object is required."))
        return

    service = _text(provider.get("service"))
    if service is None:
        errors.append(_error(f"{label}_service_required", f"{label}.service is required."))
    if not _private_https_url(url):
        errors.append(
            _error(
                f"{label}_url_invalid",
                f"{label}.url must be an HTTPS URL and not localhost.",
            )
        )
    elif runtime_url is not None and url != runtime_url:
        errors.append(
            _error(
                f"{label}_url_mismatch",
                f"{label}.url must match the configured runtime URL.",
            )
        )


def _validate_auth(
    auth: Mapping[str, object] | None,
    errors: list[SafetyGatewayManifestError],
) -> None:
    if auth is None:
        errors.append(_error("auth_required", "auth object is required."))
        return

    mode = _text(auth.get("mode"))
    if mode not in ALLOWED_AUTH_MODES:
        errors.append(
            _error(
                "auth_mode_invalid",
                "auth.mode must be bearer_token or service_identity.",
            )
        )
        return

    if mode == "bearer_token" and _text(auth.get("secret_name")) is None:
        errors.append(
            _error("auth_secret_required", "bearer_token auth requires auth.secret_name.")
        )


def _validate_network(
    network: Mapping[str, object] | None,
    errors: list[SafetyGatewayManifestError],
) -> None:
    if network is None:
        errors.append(_error("network_required", "network object is required."))
        return

    if _text(network.get("ingress")) not in {"internal_only", "private_ingress"}:
        errors.append(
            _error(
                "network_ingress_must_be_private",
                "network.ingress must restrict provider access to the backend/private network.",
            )
        )
    if _text(network.get("backend_access")) not in {"service_identity", "private_network"}:
        errors.append(
            _error(
                "backend_access_invalid",
                "network.backend_access must be service_identity or private_network.",
            )
        )


def _validate_timeout(
    timeout_seconds: float | None,
    settings: Settings,
    errors: list[SafetyGatewayManifestError],
) -> None:
    if timeout_seconds is None or timeout_seconds <= 0 or timeout_seconds > 60:
        errors.append(
            _error("timeout_seconds_invalid", "timeout_seconds must be from 0 to 60.")
        )
        return
    if timeout_seconds != settings.safety_provider_timeout_seconds:
        errors.append(
            _error(
                "timeout_seconds_mismatch",
                "timeout_seconds must match PHARMAIDE_SAFETY_PROVIDER_TIMEOUT_SECONDS.",
            )
        )


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _private_https_url(value: str | None) -> bool:
    parsed = urlparse(value or "")
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    hostname = parsed.hostname or ""
    return hostname not in {"localhost", "127.0.0.1", "0.0.0.0"}


def _error(code: str, message: str) -> SafetyGatewayManifestError:
    return SafetyGatewayManifestError(code=code, message=message)


def manifest_json_example() -> str:
    """Return an operator-friendly example manifest."""
    return json.dumps(
        {
            "environment": "staging",
            "provider": "remote_http",
            "guard": {
                "service": "llama_guard",
                "url": "https://llama-guard.internal.example/v1/guard/check",
            },
            "referee": {
                "service": "agentdog",
                "url": "https://agentdog.internal.example/v1/referee/review",
            },
            "auth": {
                "mode": "bearer_token",
                "secret_name": "projects/pharmaide/secrets/safety-provider-api-key",
            },
            "network": {
                "ingress": "internal_only",
                "backend_access": "service_identity",
            },
            "timeout_seconds": 10,
        },
        indent=2,
    )

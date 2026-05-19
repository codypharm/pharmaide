"""Authentication helpers for internal Cloud Tasks / Scheduler worker routes."""

from typing import cast

from google.auth.transport.requests import Request
from google.oauth2 import id_token


class InternalWorkerAuthError(Exception):
    """Raised when a service-to-service worker token cannot be trusted."""


def verify_internal_oidc_token(token: str, audience: str) -> dict[str, object]:
    """Verify a Google-issued OIDC token for a private internal worker route."""
    try:
        claims = id_token.verify_oauth2_token(token, Request(), audience=audience)
    except Exception as exc:
        raise InternalWorkerAuthError("invalid internal worker token") from exc
    return cast("dict[str, object]", claims)

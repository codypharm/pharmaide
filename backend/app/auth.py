"""Pharmacist-facing authentication dependencies.

Internal worker routes use a separate Cloud Tasks OIDC guard. This module owns
browser/API user identity: local development can still use the old
``X-Pharmaide-User-Id`` scaffold, while deployed GCIP mode requires a verified
Firebase/GCIP ID token.
"""

from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import Depends, Header, HTTPException, Request
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class CurrentActor:
    """Authenticated pharmacist actor projected into current UUID-based tables."""

    actor_id: UUID
    subject: str
    auth_mode: Literal["disabled", "gcip"]
    email: str | None = None
    workspace_id: UUID | None = None

    @property
    def kb_scope_id(self) -> UUID:
        """Use workspace scope when auth claims provide it, else local actor scope."""
        return self.workspace_id or self.actor_id


async def get_current_actor(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    dev_actor_id: Annotated[str | None, Header(alias="X-Pharmaide-User-Id")] = None,
) -> CurrentActor:
    """Resolve the current API actor from dev headers or GCIP bearer tokens."""
    settings = _request_settings(request)
    if settings.auth_mode == "disabled":
        return _dev_actor(dev_actor_id)
    return _gcip_actor(settings, authorization)


ActorDep = Annotated[CurrentActor, Depends(get_current_actor)]


async def get_current_actor_id(actor: ActorDep) -> UUID:
    """Compatibility dependency for routes still scoped by actor UUID."""
    return actor.actor_id


async def get_current_kb_scope_id(actor: ActorDep) -> UUID:
    """Resolve the scope used for clinic knowledge-base access."""
    return actor.kb_scope_id


def verify_gcip_id_token(token: str, *, project_id: str) -> dict[str, object]:
    """Verify a GCIP/Firebase ID token with Google's public certs."""
    request = google_requests.Request()
    return id_token.verify_firebase_token(token, request, audience=project_id)


def _request_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return get_settings()


def _dev_actor(dev_actor_id: str | None) -> CurrentActor:
    subject = (dev_actor_id or "anonymous").strip() or "anonymous"
    return CurrentActor(
        actor_id=_actor_uuid("dev", subject),
        subject=subject,
        auth_mode="disabled",
    )


def _gcip_actor(settings: Settings, authorization: str | None) -> CurrentActor:
    token = _bearer_token(authorization)
    try:
        claims = verify_gcip_id_token(token, project_id=settings.gcip_project_id or "")
    except (ValueError, google_auth_exceptions.GoogleAuthError) as exc:
        raise HTTPException(status_code=401, detail={"error": "invalid_auth_token"}) from exc

    subject = _claim_text(claims, "sub") or _claim_text(claims, "user_id")
    if subject is None:
        raise HTTPException(status_code=401, detail={"error": "invalid_auth_token"})

    workspace_id = _claim_uuid(claims, settings.gcip_workspace_claim)
    if settings.gcip_require_workspace_claim and workspace_id is None:
        raise HTTPException(status_code=403, detail={"error": "workspace_claim_required"})
    if settings.gcip_require_workspace_membership:
        if workspace_id is None:
            raise HTTPException(status_code=403, detail={"error": "workspace_claim_required"})
        if not _claim_includes_uuid(
            claims,
            settings.gcip_workspace_memberships_claim,
            workspace_id,
        ):
            raise HTTPException(status_code=403, detail={"error": "workspace_membership_required"})

    return CurrentActor(
        actor_id=_actor_uuid("gcip", f"{settings.gcip_project_id}:{subject}"),
        subject=subject,
        auth_mode="gcip",
        email=_claim_text(claims, "email"),
        workspace_id=workspace_id,
    )


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"error": "auth_token_required"})
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail={"error": "auth_token_required"})
    return token


def _claim_text(claims: dict[str, object], key: str) -> str | None:
    value = claims.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _claim_uuid(claims: dict[str, object], key: str) -> UUID | None:
    value = _claim_text(claims, key)
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail={"error": "invalid_auth_token"}) from exc


def _claim_includes_uuid(claims: dict[str, object], key: str, expected: UUID) -> bool:
    """Accept GCIP membership claims as a UUID list or comma-separated string."""
    value = claims.get(key)
    if isinstance(value, str):
        candidates = [part.strip() for part in value.split(",")]
    elif isinstance(value, list | tuple | set):
        candidates = [part.strip() for part in value if isinstance(part, str)]
    else:
        return False

    return str(expected) in candidates


def _actor_uuid(namespace: str, subject: str) -> UUID:
    try:
        return UUID(subject)
    except ValueError:
        return uuid5(NAMESPACE_URL, f"pharmaide:{namespace}:{subject}")

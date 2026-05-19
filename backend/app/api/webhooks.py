"""External provider webhook routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import PlainTextResponse

from app.config import Settings
from app.db.engine import get_session, get_session_factory
from app.services.whatsapp_webhook import (
    WhatsAppWebhookPayload,
    process_whatsapp_webhook,
    verify_meta_webhook_signature,
)

router = APIRouter(prefix="/webhooks")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


class WhatsAppWebhookResponse(BaseModel):
    accepted_count: int
    buffered_count: int
    scheduled_count: int
    ignored_count: int


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    settings: SettingsDep,
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> PlainTextResponse:
    """Answer Meta's webhook subscription challenge with the configured token."""
    configured_token = (
        settings.whatsapp_webhook_verify_token.get_secret_value()
        if settings.whatsapp_webhook_verify_token is not None
        else None
    )
    if (
        configured_token
        and mode == "subscribe"
        and challenge is not None
        and verify_token == configured_token
    ):
        return PlainTextResponse(challenge)

    raise HTTPException(
        status_code=403,
        detail={"error": "whatsapp_webhook_verification_failed"},
    )


@router.post("/whatsapp", response_model=WhatsAppWebhookResponse)
async def receive_whatsapp_webhook(
    request: Request,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
) -> WhatsAppWebhookResponse:
    raw_body = await request.body()
    _require_valid_signature(request, settings, raw_body)
    try:
        payload = WhatsAppWebhookPayload.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    result = await process_whatsapp_webhook(
        session,
        session_factory,
        settings,
        payload,
    )
    return WhatsAppWebhookResponse(
        accepted_count=result.accepted_count,
        buffered_count=result.buffered_count,
        scheduled_count=result.scheduled_count,
        ignored_count=result.ignored_count,
    )


def _require_valid_signature(
    request: Request,
    settings: Settings,
    raw_body: bytes,
) -> None:
    """Reject forged provider POSTs when a Meta app secret is configured."""
    if settings.whatsapp_webhook_app_secret is None:
        return

    signature = request.headers.get("x-hub-signature-256")
    secret = settings.whatsapp_webhook_app_secret.get_secret_value()
    if verify_meta_webhook_signature(raw_body, signature, secret):
        return

    raise HTTPException(
        status_code=401,
        detail={"error": "whatsapp_webhook_signature_invalid"},
    )

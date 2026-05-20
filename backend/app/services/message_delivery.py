"""Delivery worker for queued WhatsApp conversation messages."""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import AuditLogEntry, ConversationMessage, Treatment

log = structlog.get_logger(__name__)

PLACEHOLDER_PROVIDER = "internal-placeholder"
WHATSAPP_CLOUD_PROVIDER = "whatsapp-cloud-api"
DEFAULT_DELIVERY_LIMIT = 50
SYSTEM_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")


@dataclass(frozen=True)
class MessageDeliveryRunResult:
    processed_count: int
    sent_count: int
    failed_count: int


@dataclass(frozen=True)
class DeliveryAttemptResult:
    ok: bool
    provider: str
    external_message_id: str | None = None
    error_code: str | None = None
    error_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class DeliveryCallbackResult:
    accepted: bool
    reason: str
    message_id: UUID | None = None


@dataclass(frozen=True)
class WhatsAppCloudDeliveryConfig:
    access_token: str
    phone_number_id: str
    api_version: str
    base_url: str


class DeliveryProvider(Protocol):
    async def deliver(self, message: ConversationMessage) -> DeliveryAttemptResult:
        """Deliver one queued message through a provider-specific transport."""


class PlaceholderDeliveryProvider:
    async def deliver(self, message: ConversationMessage) -> DeliveryAttemptResult:
        """Pretend delivery succeeded until WhatsApp Business API is wired."""
        return DeliveryAttemptResult(
            ok=True,
            provider=PLACEHOLDER_PROVIDER,
            external_message_id=f"internal-delivery:{message.id}",
        )


class WhatsAppCloudDeliveryProvider:
    def __init__(
        self,
        config: WhatsAppCloudDeliveryConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._client = client

    async def deliver(self, message: ConversationMessage) -> DeliveryAttemptResult:
        """Send one text message through Meta's WhatsApp Cloud API."""
        try:
            response = await self._post_message(message)
        except httpx.HTTPError:
            log.exception(
                "whatsapp_delivery_transport_failed",
                message_id=str(message.id),
                treatment_id=str(message.treatment_id),
            )
            return DeliveryAttemptResult(
                ok=False,
                provider=WHATSAPP_CLOUD_PROVIDER,
                error_code="whatsapp_transport_error",
            )

        if response.status_code >= 400:
            return DeliveryAttemptResult(
                ok=False,
                provider=WHATSAPP_CLOUD_PROVIDER,
                error_code=f"whatsapp_http_{response.status_code}",
                error_metadata=_extract_provider_error_metadata(response),
            )

        provider_message_id = _extract_provider_message_id(response)
        if provider_message_id is None:
            return DeliveryAttemptResult(
                ok=False,
                provider=WHATSAPP_CLOUD_PROVIDER,
                error_code="whatsapp_invalid_response",
            )

        return DeliveryAttemptResult(
            ok=True,
            provider=WHATSAPP_CLOUD_PROVIDER,
            external_message_id=provider_message_id,
        )

    async def _post_message(self, message: ConversationMessage) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(
                _cloud_api_messages_url(self.config),
                headers=_cloud_api_headers(self.config),
                json=_cloud_api_text_payload(message),
            )

        async with httpx.AsyncClient(timeout=10) as client:
            return await client.post(
                _cloud_api_messages_url(self.config),
                headers=_cloud_api_headers(self.config),
                json=_cloud_api_text_payload(message),
            )


def build_delivery_provider(settings: Settings) -> DeliveryProvider:
    """Build the delivery provider selected by environment settings."""
    if settings.whatsapp_delivery_provider == "placeholder":
        return PlaceholderDeliveryProvider()

    return WhatsAppCloudDeliveryProvider(
        WhatsAppCloudDeliveryConfig(
            access_token=settings.whatsapp_cloud_api_access_token.get_secret_value()
            if settings.whatsapp_cloud_api_access_token is not None
            else "",
            phone_number_id=settings.whatsapp_cloud_api_phone_number_id or "",
            api_version=settings.whatsapp_cloud_api_version,
            base_url=settings.whatsapp_cloud_api_base_url,
        )
    )


async def run_message_delivery_once(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_DELIVERY_LIMIT,
    provider: DeliveryProvider | None = None,
) -> MessageDeliveryRunResult:
    """Move queued outbound WhatsApp messages through the delivery state machine."""
    messages = await _load_queued_whatsapp_messages(session, limit=limit)
    delivery_provider = provider or PlaceholderDeliveryProvider()
    sent_count = 0
    failed_count = 0

    for message in messages:
        old_status = message.status
        attempt = await _attempt_delivery(delivery_provider, message)
        if attempt.ok:
            _mark_message_sent(session, message, old_status=old_status, attempt=attempt)
            sent_count += 1
        else:
            _mark_message_failed(session, message, old_status=old_status, attempt=attempt)
            failed_count += 1

    await session.flush()
    log.info(
        "message_delivery_run_completed",
        processed_count=len(messages),
        sent_count=sent_count,
        failed_count=failed_count,
        provider=delivery_provider.__class__.__name__,
    )
    return MessageDeliveryRunResult(
        processed_count=len(messages),
        sent_count=sent_count,
        failed_count=failed_count,
    )


async def record_delivery_callback(
    session: AsyncSession,
    *,
    provider: str,
    external_message_id: str,
    status: str,
) -> DeliveryCallbackResult:
    """Record provider callback mismatches without trusting provider payload blindly."""
    message = await _load_message_by_external_id(session, external_message_id)
    if message is None:
        _audit_callback_rejected(
            session,
            resource_id=SYSTEM_RESOURCE_ID,
            message=None,
            provider=provider,
            external_message_id=external_message_id,
            status=status,
            reason="message_not_found",
        )
        await session.flush()
        return DeliveryCallbackResult(accepted=False, reason="message_not_found")

    if provider != PLACEHOLDER_PROVIDER:
        _audit_callback_rejected(
            session,
            resource_id=message.id,
            message=message,
            provider=provider,
            external_message_id=external_message_id,
            status=status,
            reason="provider_mismatch",
        )
        await session.flush()
        return DeliveryCallbackResult(
            accepted=False,
            reason="provider_mismatch",
            message_id=message.id,
        )

    log.info(
        "message_delivery_callback_accepted",
        message_id=str(message.id),
        provider=provider,
        callback_status=status,
    )
    return DeliveryCallbackResult(accepted=True, reason="accepted", message_id=message.id)


async def _attempt_delivery(
    provider: DeliveryProvider,
    message: ConversationMessage,
) -> DeliveryAttemptResult:
    try:
        return await provider.deliver(message)
    except Exception:
        log.exception(
            "message_delivery_provider_failed",
            message_id=str(message.id),
            treatment_id=str(message.treatment_id),
            provider=provider.__class__.__name__,
        )
        return DeliveryAttemptResult(
            ok=False,
            provider=provider.__class__.__name__,
            error_code="provider_exception",
        )


def _audit_callback_rejected(
    session: AsyncSession,
    *,
    resource_id: UUID,
    message: ConversationMessage | None,
    provider: str,
    external_message_id: str,
    status: str,
    reason: str,
) -> None:
    payload: dict[str, object] = {
        "external_message_id": external_message_id,
        "provider": provider,
        "expected_provider": PLACEHOLDER_PROVIDER,
        "callback_status": status,
        "reason": reason,
    }
    if message is not None:
        payload["message_id"] = str(message.id)

    session.add(
        AuditLogEntry(
            event_type="conversation_message_delivery_callback_rejected",
            resource_type="conversation_message" if message is not None else "system",
            resource_id=resource_id,
            # Provider callbacks are untrusted. Persist only routing/state
            # metadata, never message bodies or patient identifiers.
            payload=payload,
        )
    )


def _mark_message_sent(
    session: AsyncSession,
    message: ConversationMessage,
    *,
    old_status: str,
    attempt: DeliveryAttemptResult,
) -> None:
    message.status = "sent"
    message.external_message_id = attempt.external_message_id
    session.add(
        AuditLogEntry(
            event_type="conversation_message_delivery_marked_sent",
            resource_type="conversation_message",
            resource_id=message.id,
            # Message bodies may contain PHI and clinical advice. The
            # delivery audit records only routing and state metadata.
            payload={
                "treatment_id": str(message.treatment_id),
                "message_id": str(message.id),
                "channel": message.channel,
                "old_status": old_status,
                "new_status": message.status,
                "external_message_id": attempt.external_message_id,
                "provider": attempt.provider,
            },
        )
    )


def _mark_message_failed(
    session: AsyncSession,
    message: ConversationMessage,
    *,
    old_status: str,
    attempt: DeliveryAttemptResult,
) -> None:
    message.status = "failed"
    message.external_message_id = None
    session.add(
        AuditLogEntry(
            event_type="conversation_message_delivery_failed",
            resource_type="conversation_message",
            resource_id=message.id,
            # Failure audits must describe transport state, not message text.
            payload={
                "treatment_id": str(message.treatment_id),
                "message_id": str(message.id),
                "channel": message.channel,
                "old_status": old_status,
                "new_status": message.status,
                "provider": attempt.provider,
                "error_code": attempt.error_code or "unknown",
                **(attempt.error_metadata or {}),
            },
        )
    )


async def _load_queued_whatsapp_messages(
    session: AsyncSession,
    *,
    limit: int,
) -> list[ConversationMessage]:
    result = await session.execute(
        select(ConversationMessage)
        .options(
            selectinload(ConversationMessage.treatment).selectinload(Treatment.patient)
        )
        .where(
            ConversationMessage.direction == "outbound",
            ConversationMessage.channel == "whatsapp",
            ConversationMessage.status == "queued",
        )
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        .limit(limit)
    )
    return list(result.scalars())


def _cloud_api_messages_url(config: WhatsAppCloudDeliveryConfig) -> str:
    base_url = config.base_url.rstrip("/")
    api_version = config.api_version.strip("/")
    return f"{base_url}/{api_version}/{config.phone_number_id}/messages"


def _cloud_api_headers(config: WhatsAppCloudDeliveryConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.access_token}",
        "Content-Type": "application/json",
    }


def _cloud_api_text_payload(message: ConversationMessage) -> dict[str, object]:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _whatsapp_recipient_phone(message.treatment.patient.phone),
        "type": "text",
        "text": {
            "body": message.body,
            "preview_url": False,
        },
    }


def _whatsapp_recipient_phone(phone: str) -> str:
    """Cloud API recipients use country-code digits, while we store E.164."""
    return phone.removeprefix("+")


def _extract_provider_message_id(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(messages, list) or not messages:
        return None
    first = messages[0]
    if not isinstance(first, dict):
        return None
    message_id = first.get("id")
    return message_id if isinstance(message_id, str) and message_id else None


def _extract_provider_error_metadata(response: httpx.Response) -> dict[str, object]:
    """Keep useful Graph API failure metadata without copying free-text errors."""
    try:
        body: Any = response.json()
    except ValueError:
        return {}

    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return {}

    metadata: dict[str, object] = {}
    for source_key, target_key in (
        ("type", "provider_error_type"),
        ("code", "provider_error_code"),
        ("error_subcode", "provider_error_subcode"),
        ("fbtrace_id", "provider_trace_id"),
    ):
        value = error.get(source_key)
        if isinstance(value, str | int):
            metadata[target_key] = value
    return metadata


async def _load_message_by_external_id(
    session: AsyncSession,
    external_message_id: str,
) -> ConversationMessage | None:
    return await session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.external_message_id == external_message_id,
        )
    )

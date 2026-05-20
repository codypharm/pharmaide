"""Internal queued-message delivery worker endpoint."""

import json
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import AuditLogEntry, ConversationMessage
from app.services import message_delivery, task_runner


@pytest.fixture(autouse=True)
def isolate_delivery_worker_tests(
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delivery tests create treatments as setup; analysis has separate coverage."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)
    test_app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        whatsapp_delivery_provider="placeholder",
    )


@pytest.mark.usefixtures("postgres_container")
async def test_run_message_delivery_marks_queued_outbound_whatsapp_message_sent_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "DELIVERY-001")
    queued = await app_client.post(
        f"/treatments/{treatment_id}/pharmacist-messages",
        json={"message": "Please continue the current dose."},
    )
    assert queued.status_code == 201, queued.text
    message_id = UUID(queued.json()["id"])

    response = await app_client.post("/internal/message-delivery/run-once")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "processed_count": 1,
        "sent_count": 1,
        "failed_count": 0,
    }

    message = await db_session.get(ConversationMessage, message_id)
    assert message is not None
    assert message.status == "sent"
    assert message.external_message_id == f"internal-delivery:{message_id}"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_marked_sent"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "message_id": str(message_id),
        "channel": "whatsapp",
        "old_status": "queued",
        "new_status": "sent",
        "external_message_id": f"internal-delivery:{message_id}",
        "provider": "internal-placeholder",
    }
    assert "continue" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_run_message_delivery_returns_zero_when_no_messages_are_queued(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post("/internal/message-delivery/run-once")

    assert response.status_code == 200
    assert response.json() == {
        "processed_count": 0,
        "sent_count": 0,
        "failed_count": 0,
    }


@pytest.mark.usefixtures("postgres_container")
async def test_run_message_delivery_marks_message_failed_when_provider_fails(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "DELIVERY-002")
    queued = await app_client.post(
        f"/treatments/{treatment_id}/pharmacist-messages",
        json={"message": "Please call the pharmacy before changing dose."},
    )
    assert queued.status_code == 201, queued.text
    message_id = UUID(queued.json()["id"])

    result = await message_delivery.run_message_delivery_once(
        db_session,
        provider=FailingDeliveryProvider("provider_timeout"),
    )

    assert result.processed_count == 1
    assert result.sent_count == 0
    assert result.failed_count == 1

    message = await db_session.get(ConversationMessage, message_id)
    assert message is not None
    assert message.status == "failed"
    assert message.external_message_id is None

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_failed"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "message_id": str(message_id),
        "channel": "whatsapp",
        "old_status": "queued",
        "new_status": "failed",
        "provider": "internal-placeholder",
        "error_code": "provider_timeout",
    }
    assert "dose" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_run_message_delivery_marks_message_failed_when_provider_raises(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "DELIVERY-003")
    queued = await app_client.post(
        f"/treatments/{treatment_id}/pharmacist-messages",
        json={"message": "Please call the pharmacy today."},
    )
    assert queued.status_code == 201, queued.text
    message_id = UUID(queued.json()["id"])

    result = await message_delivery.run_message_delivery_once(
        db_session,
        provider=RaisingDeliveryProvider(),
    )

    assert result.processed_count == 1
    assert result.sent_count == 0
    assert result.failed_count == 1

    message = await db_session.get(ConversationMessage, message_id)
    assert message is not None
    assert message.status == "failed"
    assert message.external_message_id is None

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_failed"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "message_id": str(message_id),
        "channel": "whatsapp",
        "old_status": "queued",
        "new_status": "failed",
        "provider": "RaisingDeliveryProvider",
        "error_code": "provider_exception",
    }
    assert "pharmacy" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_cloud_delivery_provider_sends_text_message_and_audits_metadata(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "DELIVERY-004")
    queued = await app_client.post(
        f"/treatments/{treatment_id}/pharmacist-messages",
        json={"message": "Please continue the current dose."},
    )
    assert queued.status_code == 201, queued.text
    message_id = UUID(queued.json()["id"])
    seen_requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.sent-1"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await message_delivery.run_message_delivery_once(
            db_session,
            provider=message_delivery.WhatsAppCloudDeliveryProvider(
                message_delivery.WhatsAppCloudDeliveryConfig(
                    access_token="token-123",
                    phone_number_id="phone-number-id",
                    api_version="v25.0",
                    base_url="https://graph.facebook.com",
                ),
                client=client,
            ),
        )

    assert result.processed_count == 1
    assert result.sent_count == 1
    assert result.failed_count == 0
    assert len(seen_requests) == 1
    request = seen_requests[0]
    assert str(request.url) == "https://graph.facebook.com/v25.0/phone-number-id/messages"
    assert request.headers["authorization"] == "Bearer token-123"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "18005551212",
        "type": "text",
        "text": {
            "body": "Please continue the current dose.",
            "preview_url": False,
        },
    }

    message = await db_session.get(ConversationMessage, message_id)
    assert message is not None
    assert message.status == "sent"
    assert message.external_message_id == "wamid.sent-1"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_marked_sent"
        )
    )
    assert audit is not None
    assert audit.payload["provider"] == "whatsapp-cloud-api"
    assert audit.payload["external_message_id"] == "wamid.sent-1"
    assert "continue" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_cloud_delivery_provider_marks_message_failed_on_api_error(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "DELIVERY-005")
    queued = await app_client.post(
        f"/treatments/{treatment_id}/pharmacist-messages",
        json={"message": "Please call the pharmacy before changing dose."},
    )
    assert queued.status_code == 201, queued.text
    message_id = UUID(queued.json()["id"])

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Recipient is not in the allowed test list.",
                        "type": "OAuthException",
                        "code": 131030,
                        "error_subcode": 2494010,
                        "fbtrace_id": "trace-123",
                    }
                },
            )
        )
    ) as client:
        result = await message_delivery.run_message_delivery_once(
            db_session,
            provider=message_delivery.WhatsAppCloudDeliveryProvider(
                message_delivery.WhatsAppCloudDeliveryConfig(
                    access_token="token-123",
                    phone_number_id="phone-number-id",
                    api_version="v25.0",
                    base_url="https://graph.facebook.com",
                ),
                client=client,
            ),
        )

    assert result.processed_count == 1
    assert result.sent_count == 0
    assert result.failed_count == 1

    message = await db_session.get(ConversationMessage, message_id)
    assert message is not None
    assert message.status == "failed"
    assert message.external_message_id is None

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_failed"
        )
    )
    assert audit is not None
    assert audit.payload["provider"] == "whatsapp-cloud-api"
    assert audit.payload["error_code"] == "whatsapp_http_400"
    assert audit.payload["provider_error_type"] == "OAuthException"
    assert audit.payload["provider_error_code"] == 131030
    assert audit.payload["provider_error_subcode"] == 2494010
    assert audit.payload["provider_trace_id"] == "trace-123"
    assert "allowed test list" not in str(audit.payload).lower()
    assert "dose" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_delivery_callback_rejects_provider_mismatch_without_changing_message(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "DELIVERY-006")
    queued = await app_client.post(
        f"/treatments/{treatment_id}/pharmacist-messages",
        json={"message": "Please continue the current dose."},
    )
    assert queued.status_code == 201, queued.text
    message_id = UUID(queued.json()["id"])

    run_response = await app_client.post("/internal/message-delivery/run-once")
    assert run_response.status_code == 200, run_response.text

    callback_response = await app_client.post(
        "/internal/message-delivery/callback",
        json={
            "provider": "wrong-provider",
            "external_message_id": f"internal-delivery:{message_id}",
            "status": "sent",
        },
    )

    assert callback_response.status_code == 200, callback_response.text
    assert callback_response.json() == {
        "accepted": False,
        "reason": "provider_mismatch",
        "message_id": str(message_id),
    }

    message = await db_session.get(ConversationMessage, message_id)
    assert message is not None
    assert message.status == "sent"
    assert message.external_message_id == f"internal-delivery:{message_id}"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_callback_rejected"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "message_id": str(message_id),
        "external_message_id": f"internal-delivery:{message_id}",
        "provider": "wrong-provider",
        "expected_provider": "internal-placeholder",
        "callback_status": "sent",
        "reason": "provider_mismatch",
    }
    assert "continue" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_delivery_callback_marks_whatsapp_cloud_message_delivered_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "DELIVERY-007")
    message = ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="pharmacist",
        channel="whatsapp",
        status="sent",
        body="Please continue the current dose.",
        external_message_id="wamid.delivered-1",
    )
    db_session.add(message)
    await db_session.flush()

    callback_response = await app_client.post(
        "/internal/message-delivery/callback",
        json={
            "provider": "whatsapp-cloud-api",
            "external_message_id": "wamid.delivered-1",
            "status": "delivered",
        },
    )

    assert callback_response.status_code == 200, callback_response.text
    assert callback_response.json() == {
        "accepted": True,
        "reason": "accepted",
        "message_id": str(message.id),
    }

    await db_session.refresh(message)
    assert message.status == "delivered"
    assert message.external_message_id == "wamid.delivered-1"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_callback_accepted"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "message_id": str(message.id),
        "external_message_id": "wamid.delivered-1",
        "provider": "whatsapp-cloud-api",
        "callback_status": "delivered",
        "old_status": "sent",
        "new_status": "delivered",
    }
    assert "continue" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_delivery_callback_marks_whatsapp_cloud_message_failed_with_metadata(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "DELIVERY-008")
    message = ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="pharmacist",
        channel="whatsapp",
        status="sent",
        body="Please continue the current dose.",
        external_message_id="wamid.failed-1",
    )
    db_session.add(message)
    await db_session.flush()

    callback_response = await app_client.post(
        "/internal/message-delivery/callback",
        json={
            "provider": "whatsapp-cloud-api",
            "external_message_id": "wamid.failed-1",
            "status": "failed",
        },
    )

    assert callback_response.status_code == 200, callback_response.text
    await db_session.refresh(message)
    assert message.status == "failed"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_callback_accepted"
        )
    )
    assert audit is not None
    assert audit.payload["callback_status"] == "failed"
    assert audit.payload["old_status"] == "sent"
    assert audit.payload["new_status"] == "failed"
    assert "dose" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_delivery_callback_rejects_status_regression_without_changing_message(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "DELIVERY-009")
    message = ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="pharmacist",
        channel="whatsapp",
        status="read",
        body="Please continue the current dose.",
        external_message_id="wamid.read-1",
    )
    db_session.add(message)
    await db_session.flush()

    callback_response = await app_client.post(
        "/internal/message-delivery/callback",
        json={
            "provider": "whatsapp-cloud-api",
            "external_message_id": "wamid.read-1",
            "status": "delivered",
        },
    )

    assert callback_response.status_code == 200, callback_response.text
    assert callback_response.json() == {
        "accepted": False,
        "reason": "status_regression",
        "message_id": str(message.id),
    }

    await db_session.refresh(message)
    assert message.status == "read"


class FailingDeliveryProvider:
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code

    async def deliver(
        self,
        message: ConversationMessage,
    ) -> message_delivery.DeliveryAttemptResult:
        return message_delivery.DeliveryAttemptResult(
            ok=False,
            provider=message_delivery.PLACEHOLDER_PROVIDER,
            external_message_id=None,
            error_code=self.error_code,
        )


class RaisingDeliveryProvider:
    async def deliver(
        self,
        message: ConversationMessage,
    ) -> message_delivery.DeliveryAttemptResult:
        raise RuntimeError("provider transport failed")


async def _create_treatment(app_client: AsyncClient, mrn: str) -> UUID:
    response = await app_client.post(
        "/treatments",
        json={
            "patient": {
                "name": "Eleanor Vance",
                "dob": "1955-10-12",
                "mrn": mrn,
                "phone": "+18005551212",
            },
            "treatment": {"clinical_objective": "Monitor recovery"},
            "medications": [
                {
                    "name": "Amoxicillin",
                    "dosage": "500 mg",
                    "frequency": "Three Times Daily (TID)",
                    "duration": "7 days",
                    "objective": None,
                }
            ],
            "ingestion_method": "structured",
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["treatment_id"])

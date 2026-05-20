"""WhatsApp inbound webhook buffering."""

import hashlib
import hmac
import json
from datetime import date

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AuditLogEntry, ConversationMessage, Patient, Treatment
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Webhook tests create treatment rows directly or suppress analysis fanout."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


async def test_whatsapp_webhook_verification_returns_challenge(
    test_app: FastAPI,
    app_client: AsyncClient,
) -> None:
    test_app.state.settings = Settings(
        _env_file=None,
        whatsapp_webhook_verify_token="verify-me",
    )

    response = await app_client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 200
    assert response.text == "challenge-123"


async def test_whatsapp_webhook_verification_requires_configured_token(
    test_app: FastAPI,
    app_client: AsyncClient,
) -> None:
    test_app.state.settings = Settings(_env_file=None, whatsapp_webhook_verify_token=None)

    response = await app_client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 403


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_webhook_buffers_text_message_and_schedules_turn_processing(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment = await _persist_active_treatment(db_session)
    scheduled: list[task_runner.BackgroundJob] = []

    def capture_schedule_job(
        job: task_runner.BackgroundJob,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        scheduled.append(job)

    monkeypatch.setattr(task_runner, "schedule_job", capture_schedule_job)

    response = await app_client.post(
        "/webhooks/whatsapp",
        json=_message_payload(from_phone="18005551212", message="I took it but I feel dizzy"),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "accepted_count": 1,
        "buffered_count": 1,
        "scheduled_count": 1,
        "ignored_count": 0,
    }

    message = await db_session.scalar(select(ConversationMessage))
    assert message is not None
    assert message.treatment_id == treatment.id
    assert message.direction == "inbound"
    assert message.sender_type == "patient"
    assert message.channel == "whatsapp"
    assert message.status == "received"
    assert message.body == "I took it but I feel dizzy"

    assert len(scheduled) == 1
    job = scheduled[0]
    assert job.name == "patient-turn.process"
    assert job.payload == {
        "treatment_id": str(treatment.id),
        "schedule_delay_seconds": 5,
    }
    assert "dizzy" not in str(job.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_webhook_accepts_valid_signed_request(
    test_app: FastAPI,
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_app.state.settings = Settings(_env_file=None, whatsapp_webhook_app_secret="app-secret")
    treatment = await _persist_active_treatment(db_session)
    scheduled: list[task_runner.BackgroundJob] = []
    monkeypatch.setattr(
        task_runner,
        "schedule_job",
        lambda job, *args, **kwargs: scheduled.append(job),
    )

    body = _json_body(_message_payload(from_phone="18005551212", message="I took it"))
    response = await app_client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": _meta_signature(body, "app-secret"),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["buffered_count"] == 1
    assert (await db_session.scalar(select(ConversationMessage))).treatment_id == treatment.id
    assert len(scheduled) == 1


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_webhook_rejects_invalid_signature_without_buffering(
    test_app: FastAPI,
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_app.state.settings = Settings(_env_file=None, whatsapp_webhook_app_secret="app-secret")
    await _persist_active_treatment(db_session)
    scheduled: list[task_runner.BackgroundJob] = []
    monkeypatch.setattr(
        task_runner,
        "schedule_job",
        lambda job, *args, **kwargs: scheduled.append(job),
    )

    response = await app_client.post(
        "/webhooks/whatsapp",
        json=_message_payload(from_phone="18005551212", message="I took it"),
        headers={"x-hub-signature-256": "sha256=bad"},
    )

    assert response.status_code == 401
    assert await db_session.scalar(select(ConversationMessage)) is None
    assert scheduled == []


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_webhook_acknowledges_unknown_patient_without_buffering(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled: list[task_runner.BackgroundJob] = []
    monkeypatch.setattr(
        task_runner,
        "schedule_job",
        lambda job, *args, **kwargs: scheduled.append(job),
    )

    response = await app_client.post(
        "/webhooks/whatsapp",
        json=_message_payload(from_phone="18005550000", message="hello"),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "accepted_count": 1,
        "buffered_count": 0,
        "scheduled_count": 0,
        "ignored_count": 1,
    }
    assert await db_session.scalar(select(ConversationMessage)) is None
    assert scheduled == []


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_webhook_ignores_blank_text_without_buffering(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _persist_active_treatment(db_session)
    scheduled: list[task_runner.BackgroundJob] = []
    monkeypatch.setattr(
        task_runner,
        "schedule_job",
        lambda job, *args, **kwargs: scheduled.append(job),
    )

    response = await app_client.post(
        "/webhooks/whatsapp",
        json=_message_payload(from_phone="18005551212", message="   "),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "accepted_count": 0,
        "buffered_count": 0,
        "scheduled_count": 0,
        "ignored_count": 0,
    }
    assert await db_session.scalar(select(ConversationMessage)) is None
    assert scheduled == []


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_webhook_ignores_ambiguous_active_phone_match(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _persist_active_treatment(db_session, mrn="WHATSAPP-001")
    await _persist_active_treatment(db_session, mrn="WHATSAPP-002")
    scheduled: list[task_runner.BackgroundJob] = []
    monkeypatch.setattr(
        task_runner,
        "schedule_job",
        lambda job, *args, **kwargs: scheduled.append(job),
    )

    response = await app_client.post(
        "/webhooks/whatsapp",
        json=_message_payload(from_phone="18005551212", message="hello"),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "accepted_count": 1,
        "buffered_count": 0,
        "scheduled_count": 0,
        "ignored_count": 1,
    }
    assert await db_session.scalar(select(ConversationMessage)) is None
    assert scheduled == []


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_webhook_records_delivery_status_callback(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment = await _persist_active_treatment(db_session)
    message = ConversationMessage(
        treatment_id=treatment.id,
        direction="outbound",
        sender_type="pharmacist",
        channel="whatsapp",
        status="sent",
        body="Please continue the current dose.",
        external_message_id="wamid.status-1",
    )
    db_session.add(message)
    await db_session.flush()
    scheduled: list[task_runner.BackgroundJob] = []
    monkeypatch.setattr(
        task_runner,
        "schedule_job",
        lambda job, *args, **kwargs: scheduled.append(job),
    )

    response = await app_client.post(
        "/webhooks/whatsapp",
        json=_status_payload(message_id="wamid.status-1", status="delivered"),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "accepted_count": 1,
        "buffered_count": 0,
        "scheduled_count": 0,
        "ignored_count": 0,
    }
    await db_session.refresh(message)
    assert message.status == "delivered"
    assert scheduled == []

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_callback_accepted"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "message_id": str(message.id),
        "external_message_id": "wamid.status-1",
        "provider": "whatsapp-cloud-api",
        "callback_status": "delivered",
        "old_status": "sent",
        "new_status": "delivered",
    }
    assert "continue" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_webhook_counts_unmatched_delivery_status_as_ignored(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await app_client.post(
        "/webhooks/whatsapp",
        json=_status_payload(message_id="wamid.unknown", status="delivered"),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "accepted_count": 1,
        "buffered_count": 0,
        "scheduled_count": 0,
        "ignored_count": 1,
    }
    assert await db_session.scalar(select(ConversationMessage)) is None


@pytest.mark.usefixtures("postgres_container")
async def test_whatsapp_webhook_records_failed_delivery_status_metadata_without_free_text(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment = await _persist_active_treatment(db_session)
    message = ConversationMessage(
        treatment_id=treatment.id,
        direction="outbound",
        sender_type="pharmacist",
        channel="whatsapp",
        status="sent",
        body="Please continue the current dose.",
        external_message_id="wamid.failed-status-1",
    )
    db_session.add(message)
    await db_session.flush()

    response = await app_client.post(
        "/webhooks/whatsapp",
        json=_status_payload(
            message_id="wamid.failed-status-1",
            status="failed",
            errors=[
                {
                    "code": 131026,
                    "title": "Message undeliverable",
                    "message": "Recipient phone number is not currently reachable.",
                    "error_data": {"details": "Free-text provider details"},
                }
            ],
        ),
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(message)
    assert message.status == "failed"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_callback_accepted"
        )
    )
    assert audit is not None
    assert audit.payload["provider_error_code"] == 131026
    assert audit.payload["provider_error_count"] == 1
    assert "undeliverable" not in str(audit.payload).lower()
    assert "reachable" not in str(audit.payload).lower()
    assert "details" not in str(audit.payload).lower()
    assert "continue" not in str(audit.payload).lower()


async def _persist_active_treatment(
    session: AsyncSession,
    *,
    mrn: str = "WHATSAPP-001",
) -> Treatment:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn=mrn,
        phone="+18005551212",
    )
    treatment = Treatment(
        patient=patient,
        status="active",
        automation_mode="active",
        clinical_objective="Monitor recovery",
    )
    session.add(treatment)
    await session.flush()
    return treatment


def _message_payload(*, from_phone: str, message: str) -> dict[str, object]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": "wamid.test-message-1",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": message},
                                }
                            ]
                        }
                    }
                ]
            }
        ],
    }


def _status_payload(
    *,
    message_id: str,
    status: str,
    errors: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    status_item: dict[str, object] = {
        "id": message_id,
        "status": status,
        "timestamp": "1710000001",
        "recipient_id": "18005551212",
    }
    if errors is not None:
        status_item["errors"] = errors

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [status_item]
                        }
                    }
                ]
            }
        ],
    }


def _json_body(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _meta_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"

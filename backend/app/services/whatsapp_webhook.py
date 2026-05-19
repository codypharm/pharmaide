"""Inbound WhatsApp webhook buffering.

The webhook stores text messages in `conversation_messages`, then schedules the
existing buffered-turn worker. Queue payloads contain only treatment ids and
timing metadata; patient message text stays in the database row.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import Patient, Treatment
from app.services import patient_message_worker, task_runner
from app.services.patient_message_buffer import (
    DEFAULT_BUFFER_MINIMUM_AGE,
    buffer_patient_message,
)

log = structlog.get_logger(__name__)


class WhatsAppText(BaseModel):
    model_config = ConfigDict(extra="ignore")

    body: str = Field(min_length=1)


class WhatsAppMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    from_phone: Annotated[str, Field(alias="from")]
    provider_message_id: Annotated[str, Field(alias="id")]
    type: str
    text: WhatsAppText | None = None


class WhatsAppWebhookValue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    messages: list[WhatsAppMessage] = Field(default_factory=list)


class WhatsAppWebhookChange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: WhatsAppWebhookValue


class WhatsAppWebhookEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    changes: list[WhatsAppWebhookChange] = Field(default_factory=list)


class WhatsAppWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entry: list[WhatsAppWebhookEntry] = Field(default_factory=list)


@dataclass(frozen=True)
class WhatsAppWebhookResult:
    accepted_count: int
    buffered_count: int
    scheduled_count: int
    ignored_count: int


async def process_whatsapp_webhook(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    payload: WhatsAppWebhookPayload,
) -> WhatsAppWebhookResult:
    """Buffer inbound WhatsApp text messages and enqueue the turn processor."""
    buffered_count = 0
    scheduled_count = 0
    ignored_count = 0
    messages = list(_text_messages(payload))

    for message in messages:
        treatment_id = await _resolve_active_treatment_id(session, message.from_phone)
        if treatment_id is None:
            ignored_count += 1
            continue

        await buffer_patient_message(
            session,
            treatment_id=treatment_id,
            message=message.text.body if message.text is not None else "",
        )
        buffered_count += 1
        _schedule_buffered_turn_processing(
            session_factory,
            settings,
            treatment_id=treatment_id,
        )
        scheduled_count += 1

    log.info(
        "whatsapp_webhook_processed",
        accepted_count=len(messages),
        buffered_count=buffered_count,
        scheduled_count=scheduled_count,
        ignored_count=ignored_count,
    )
    return WhatsAppWebhookResult(
        accepted_count=len(messages),
        buffered_count=buffered_count,
        scheduled_count=scheduled_count,
        ignored_count=ignored_count,
    )


def _text_messages(payload: WhatsAppWebhookPayload) -> list[WhatsAppMessage]:
    messages: list[WhatsAppMessage] = []
    for entry in payload.entry:
        for change in entry.changes:
            for message in change.value.messages:
                if (
                    message.type == "text"
                    and message.text is not None
                    and message.text.body.strip()
                ):
                    messages.append(message)
    return messages


async def _resolve_active_treatment_id(
    session: AsyncSession,
    whatsapp_from: str,
) -> UUID | None:
    phone = _normalise_whatsapp_phone(whatsapp_from)
    result = await session.execute(
        select(Treatment.id)
        .join(Patient)
        .where(
            Patient.phone == phone,
            Treatment.status == "active",
            Treatment.archived_at.is_(None),
        )
        .order_by(Treatment.created_at.desc(), Treatment.id.desc())
        .limit(2)
    )
    treatment_ids = list(result.scalars())
    if len(treatment_ids) != 1:
        return None
    return treatment_ids[0]


def _normalise_whatsapp_phone(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("+"):
        return stripped
    return f"+{stripped}"


def _schedule_buffered_turn_processing(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    treatment_id: UUID,
) -> None:
    delay_seconds = int(DEFAULT_BUFFER_MINIMUM_AGE.total_seconds())
    task_runner.schedule_job(
        task_runner.BackgroundJob(
            name="patient-turn.process",
            idempotency_key=f"patient-turn:{treatment_id}:{int(time.time() // delay_seconds)}",
            payload={
                "treatment_id": str(treatment_id),
                "schedule_delay_seconds": delay_seconds,
            },
        ),
        _run_buffered_turn_processing,
        session_factory,
        treatment_id,
        settings,
        delay_seconds,
    )


async def _run_buffered_turn_processing(
    session_factory: async_sessionmaker[AsyncSession],
    treatment_id: UUID,
    settings: Settings,
    delay_seconds: int,
) -> None:
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    async with session_factory() as session, session.begin():
        await patient_message_worker.process_buffered_patient_messages_for_treatment(
            session,
            treatment_id=treatment_id,
            settings=settings,
        )

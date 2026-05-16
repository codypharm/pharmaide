"""Patient message burst buffering.

WhatsApp patients often send several short messages in quick succession. This
service stores each inbound message once, then aggregates unprocessed rows into
a single turn for the patient-reply pipeline. It keeps PHI in
conversation_messages and writes only metadata to audit rows.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, ConversationMessage, Treatment

log = structlog.get_logger(__name__)

BufferedTurnHandler = Callable[["BufferedPatientTurn"], Awaitable[None]]


class TreatmentNotFound(Exception):
    """Raised when a buffered message references a missing treatment."""


@dataclass(frozen=True)
class BufferedPatientTurn:
    treatment_id: UUID
    message_ids: list[UUID]
    message_text: str


@dataclass(frozen=True)
class ProcessBufferedTurnResult:
    processed_count: int


async def buffer_patient_message(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    message: str,
) -> ConversationMessage:
    """Store one inbound patient message for later turn aggregation."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    inbound = ConversationMessage(
        treatment_id=treatment_id,
        direction="inbound",
        sender_type="patient",
        channel="whatsapp",
        status="received",
        body=_required_text(message),
    )
    session.add(inbound)
    await session.flush()
    _audit_buffered_message(session, treatment_id=treatment_id, message=inbound)
    await session.flush()
    log.info(
        "patient_message_buffered",
        treatment_id=str(treatment_id),
        message_id=str(inbound.id),
        channel=inbound.channel,
    )
    return inbound


async def process_buffered_patient_turn(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    handle_turn: BufferedTurnHandler,
    limit: int = 10,
) -> ProcessBufferedTurnResult:
    """Aggregate unprocessed patient messages and hand them to a turn handler."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    messages = await _load_unprocessed_messages(session, treatment_id=treatment_id, limit=limit)
    if not messages:
        return ProcessBufferedTurnResult(processed_count=0)

    turn = BufferedPatientTurn(
        treatment_id=treatment_id,
        message_ids=[message.id for message in messages],
        message_text="\n".join(message.body for message in messages),
    )
    await handle_turn(turn)

    processed_at = datetime.now(UTC)
    for message in messages:
        message.processed_at = processed_at
    await session.flush()

    _audit_processed_turn(session, turn)
    await session.flush()
    log.info(
        "patient_message_buffer_processed",
        treatment_id=str(treatment_id),
        processed_count=len(messages),
    )
    return ProcessBufferedTurnResult(processed_count=len(messages))


async def _load_unprocessed_messages(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    limit: int,
) -> list[ConversationMessage]:
    result = await session.execute(
        select(ConversationMessage)
        .where(
            ConversationMessage.treatment_id == treatment_id,
            ConversationMessage.direction == "inbound",
            ConversationMessage.sender_type == "patient",
            ConversationMessage.status == "received",
            ConversationMessage.processed_at.is_(None),
        )
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        .limit(limit)
    )
    return list(result.scalars())


def _audit_buffered_message(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    message: ConversationMessage,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="patient_message_buffered",
            resource_type="conversation_message",
            resource_id=message.id,
            # Message text may contain PHI or symptoms. Store only intake
            # metadata in the audit trail.
            payload={
                "treatment_id": str(treatment_id),
                "message_id": str(message.id),
                "channel": message.channel,
                "status": message.status,
            },
        )
    )


def _audit_processed_turn(session: AsyncSession, turn: BufferedPatientTurn) -> None:
    session.add(
        AuditLogEntry(
            event_type="patient_message_buffer_processed",
            resource_type="treatment",
            resource_id=turn.treatment_id,
            # The aggregate text remains in conversation_messages only.
            payload={
                "treatment_id": str(turn.treatment_id),
                "message_ids": [str(message_id) for message_id in turn.message_ids],
                "processed_count": len(turn.message_ids),
                "aggregate_message_present": bool(turn.message_text),
            },
        )
    )


def _required_text(message: str) -> str:
    stripped = message.strip()
    if not stripped:
        raise ValueError("message must not be blank")
    return stripped

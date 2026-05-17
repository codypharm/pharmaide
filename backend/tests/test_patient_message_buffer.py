"""Buffered patient message turn aggregation."""

import asyncio
import json
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models import AuditLogEntry, ConversationMessage, Patient, Treatment
from app.services.patient_message_buffer import (
    buffer_patient_message,
    process_buffered_patient_turn,
)


async def test_process_buffered_patient_turn_aggregates_received_messages_once(
    db_session: AsyncSession,
) -> None:
    treatment = await _persist_treatment(db_session)
    await buffer_patient_message(db_session, treatment_id=treatment.id, message="I took it")
    await buffer_patient_message(db_session, treatment_id=treatment.id, message="but I vomited")
    await _age_buffered_messages(db_session, treatment.id)
    seen: dict[str, object] = {}

    async def handle_turn(turn: object) -> None:
        seen["text"] = turn.message_text
        seen["message_count"] = len(turn.message_ids)

    first = await process_buffered_patient_turn(
        db_session,
        treatment_id=treatment.id,
        handle_turn=handle_turn,
    )
    second = await process_buffered_patient_turn(
        db_session,
        treatment_id=treatment.id,
        handle_turn=handle_turn,
    )

    messages = (
        await db_session.execute(
            select(ConversationMessage).order_by(ConversationMessage.created_at.asc())
        )
    ).scalars().all()
    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "patient_message_buffer_processed")
    )

    assert first.processed_count == 2
    assert second.processed_count == 0
    assert seen == {"text": "I took it\nbut I vomited", "message_count": 2}
    assert all(message.processed_at is not None for message in messages)
    assert audit is not None
    assert audit.payload == {
        "treatment_id": str(treatment.id),
        "message_ids": [str(message.id) for message in messages],
        "processed_count": 2,
        "aggregate_message_present": True,
    }
    assert "vomited" not in json.dumps(audit.payload).lower()


async def test_process_buffered_patient_turn_waits_for_debounce_window(
    db_session: AsyncSession,
) -> None:
    treatment = await _persist_treatment(db_session, mrn="BUFFER-003")
    message = await buffer_patient_message(
        db_session,
        treatment_id=treatment.id,
        message="I just sent this",
    )
    message.created_at = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
    await db_session.flush()
    seen: dict[str, object] = {}

    async def handle_turn(turn: object) -> None:
        seen["text"] = turn.message_text

    too_soon = await process_buffered_patient_turn(
        db_session,
        treatment_id=treatment.id,
        handle_turn=handle_turn,
        now=datetime(2026, 5, 16, 12, 0, 4, tzinfo=UTC),
        minimum_age=timedelta(seconds=5),
    )
    old_enough = await process_buffered_patient_turn(
        db_session,
        treatment_id=treatment.id,
        handle_turn=handle_turn,
        now=datetime(2026, 5, 16, 12, 0, 5, tzinfo=UTC),
        minimum_age=timedelta(seconds=5),
    )

    assert too_soon.processed_count == 0
    assert old_enough.processed_count == 1
    assert seen == {"text": "I just sent this"}


async def test_process_buffered_patient_turn_leaves_messages_unprocessed_when_handler_fails(
    db_session: AsyncSession,
) -> None:
    treatment = await _persist_treatment(db_session, mrn="BUFFER-002")
    await buffer_patient_message(db_session, treatment_id=treatment.id, message="I feel worse")
    await _age_buffered_messages(db_session, treatment.id)

    async def fail_turn(turn: object) -> None:
        raise RuntimeError("reply pipeline failed")

    with suppress(RuntimeError):
        await process_buffered_patient_turn(
            db_session,
            treatment_id=treatment.id,
            handle_turn=fail_turn,
        )

    message = await db_session.scalar(select(ConversationMessage))
    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "patient_message_buffer_processed")
    )
    assert message is not None
    assert message.processed_at is None
    assert audit is None


async def test_process_buffered_patient_turn_skips_messages_claimed_by_another_worker(
    db_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as setup_session:
        treatment = await _persist_treatment(setup_session, mrn="BUFFER-LOCK-001")
        await buffer_patient_message(
            setup_session,
            treatment_id=treatment.id,
            message="I took it",
        )
        await _age_buffered_messages(setup_session, treatment.id)
        await setup_session.commit()
        treatment_id = treatment.id

    first_worker_claimed = asyncio.Event()
    release_first_worker = asyncio.Event()

    async def slow_handle_turn(turn: object) -> None:
        first_worker_claimed.set()
        await release_first_worker.wait()

    async def first_worker() -> object:
        async with session_factory() as session:
            result = await process_buffered_patient_turn(
                session,
                treatment_id=treatment_id,
                handle_turn=slow_handle_turn,
            )
            await session.commit()
            return result

    async def unexpected_duplicate_handler(turn: object) -> None:
        raise AssertionError("locked messages must not be handed to a second worker")

    try:
        first_task = asyncio.create_task(first_worker())
        await first_worker_claimed.wait()

        async with session_factory() as second_session:
            second = await process_buffered_patient_turn(
                second_session,
                treatment_id=treatment_id,
                handle_turn=unexpected_duplicate_handler,
            )
            await second_session.commit()

        release_first_worker.set()
        first = await first_task

        assert first.processed_count == 1
        assert second.processed_count == 0
    finally:
        release_first_worker.set()
        async with session_factory() as cleanup_session:
            await cleanup_session.execute(delete(Treatment).where(Treatment.id == treatment_id))
            await cleanup_session.commit()


async def _persist_treatment(session: AsyncSession, mrn: str = "BUFFER-001") -> Treatment:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn=mrn,
        phone="+18005551212",
    )
    treatment = Treatment(patient=patient, clinical_objective="Monitor recovery")
    session.add(treatment)
    await session.flush()
    return treatment


async def _age_buffered_messages(session: AsyncSession, treatment_id: object) -> None:
    messages = (
        await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.treatment_id == treatment_id)
            .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        )
    ).scalars().all()
    old_enough = datetime.now(UTC) - timedelta(seconds=10)
    for index, message in enumerate(messages):
        message.created_at = old_enough + timedelta(milliseconds=index)
    await session.flush()

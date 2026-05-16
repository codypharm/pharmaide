"""Capture structured monitoring state from patient WhatsApp replies.

This module prefers the low-latency PydanticAI classifier when configured,
then falls back to deterministic matching when the model is unavailable. Both
paths return the same validated `PatientReplyClassification` contract before
they mutate adherence or check-in state.
"""

import re
from datetime import UTC, datetime
from uuid import UUID

import structlog
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.patient_reply_classifier import (
    PatientReplyClassification,
    classify_patient_reply_with_agent,
)
from app.api.schemas import AdherenceEventCreate, PatientCheckInCreate, TriageReason
from app.db.models import AuditLogEntry, ConversationMessage
from app.services.adherence_events import (
    MedicationNotFound as AdherenceMedicationNotFound,
)
from app.services.adherence_events import (
    create_adherence_event,
)
from app.services.patient_checkins import create_patient_check_in

log = structlog.get_logger(__name__)

TAKEN_PATTERNS = (
    r"\btaken\b",
    r"\btook\b",
    r"\bdone\b",
    r"\byes\b",
    r"\bi have taken\b",
    r"\bi took\b",
)
MISSED_PATTERNS = (
    r"\bmissed\b",
    r"\bforgot\b",
    r"\bskipped\b",
    r"\bdid not take\b",
    r"\bdidn't take\b",
    r"\bnot taken\b",
)
SIDE_EFFECT_PATTERNS = (
    r"\bvomit",
    r"\bnausea",
    r"\brash\b",
    r"\bdizz",
    r"\bswell",
    r"\bbleed",
    r"\bdiarrhea\b",
    r"\ballerg",
    r"\bfaint",
)
NOT_IMPROVING_PATTERNS = (
    r"\bnot better\b",
    r"\bnot improving\b",
    r"\bno improvement\b",
    r"\bworse\b",
    r"\bstill sick\b",
)


class ReminderCaptureContext(BaseModel):
    """Metadata-only link between a patient reply and the latest reminder."""

    medication_id: UUID
    reminder_key: str


async def capture_patient_reply_state(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    inbound_message: ConversationMessage,
    classifier_agent: Agent[None, PatientReplyClassification] | None = None,
) -> PatientReplyClassification:
    """Create adherence state when an inbound reply clearly answers a reminder."""
    classification = await _classify_patient_reply(
        inbound_message.body,
        classifier_agent=classifier_agent,
    )
    if classification.intent in {"side_effect", "not_improving"}:
        await _create_patient_status_check_in(
            session,
            treatment_id=treatment_id,
            inbound_message=inbound_message,
            classification=classification,
        )
        return classification

    if classification.intent not in {"taken", "missed"}:
        return classification

    context = await _latest_reminder_context(session, treatment_id=treatment_id)
    if context is None:
        log.info(
            "patient_reply_adherence_skipped",
            treatment_id=str(treatment_id),
            inbound_message_id=str(inbound_message.id),
            reason="no_recent_reminder",
            intent=classification.intent,
        )
        return classification

    if await _reply_already_captured(
        session,
        treatment_id=treatment_id,
        reminder_key=context.reminder_key,
        status=classification.intent,
    ):
        log.info(
            "patient_reply_adherence_skipped",
            treatment_id=str(treatment_id),
            inbound_message_id=str(inbound_message.id),
            reason="reminder_already_captured",
            intent=classification.intent,
        )
        return classification

    try:
        await create_adherence_event(
            session,
            treatment_id,
            AdherenceEventCreate(
                medication_id=context.medication_id,
                status=classification.intent,
                source="patient",
                occurred_at=datetime.now(UTC),
            ),
        )
    except AdherenceMedicationNotFound:
        log.warning(
            "patient_reply_adherence_skipped",
            treatment_id=str(treatment_id),
            inbound_message_id=str(inbound_message.id),
            reason="reminder_medication_missing",
            medication_id=str(context.medication_id),
        )
        return classification

    _audit_patient_reply_adherence_capture(
        session,
        treatment_id=treatment_id,
        inbound_message=inbound_message,
        context=context,
        status=classification.intent,
    )
    await session.flush()
    log.info(
        "patient_reply_adherence_captured",
        treatment_id=str(treatment_id),
        inbound_message_id=str(inbound_message.id),
        medication_id=str(context.medication_id),
        status=classification.intent,
    )
    return classification


def classify_patient_reply(message: str) -> PatientReplyClassification:
    """Classify short reminder replies without asking the LLM to infer state."""
    normalised = _normalise_message(message)
    if _matches_any(normalised, SIDE_EFFECT_PATTERNS):
        return PatientReplyClassification(intent="side_effect", confidence=0.86)
    if _matches_any(normalised, NOT_IMPROVING_PATTERNS):
        return PatientReplyClassification(intent="not_improving", confidence=0.82)
    if _matches_any(normalised, MISSED_PATTERNS):
        return PatientReplyClassification(intent="missed", confidence=0.92)
    if _matches_any(normalised, TAKEN_PATTERNS):
        return PatientReplyClassification(intent="taken", confidence=0.9)
    return PatientReplyClassification(intent="general", confidence=0.5)


async def _classify_patient_reply(
    message: str,
    *,
    classifier_agent: Agent[None, PatientReplyClassification] | None,
) -> PatientReplyClassification:
    if classifier_agent is None:
        return classify_patient_reply(message)
    try:
        return await classify_patient_reply_with_agent(message, agent=classifier_agent)
    except Exception as exc:
        log.warning(
            "patient_reply_classifier_fallback",
            error_type=exc.__class__.__name__,
        )
        return classify_patient_reply(message)


def triage_reason_for_patient_reply(
    classification: PatientReplyClassification,
) -> TriageReason | None:
    """Map patient-state captures to pharmacist-review routing."""
    if classification.intent == "side_effect":
        return "side_effect"
    if classification.intent == "not_improving":
        return "unclear_message"
    return None


async def _create_patient_status_check_in(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    inbound_message: ConversationMessage,
    classification: PatientReplyClassification,
) -> None:
    report_type = "side_effect" if classification.intent == "side_effect" else "not_improving"
    await create_patient_check_in(
        session,
        treatment_id,
        PatientCheckInCreate(
            report_type=report_type,
            source="patient",
            message=inbound_message.body,
            observed_at=datetime.now(UTC),
        ),
    )
    log.info(
        "patient_reply_check_in_captured",
        treatment_id=str(treatment_id),
        inbound_message_id=str(inbound_message.id),
        report_type=report_type,
    )


async def _latest_reminder_context(
    session: AsyncSession,
    *,
    treatment_id: UUID,
) -> ReminderCaptureContext | None:
    result = await session.execute(
        select(AuditLogEntry)
        .where(
            AuditLogEntry.event_type == "monitoring_message_queued",
            AuditLogEntry.payload.contains({"treatment_id": str(treatment_id)}),
        )
        .order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
        .limit(1)
    )
    audit = result.scalar_one_or_none()
    if audit is None:
        return None

    reminder_key = audit.payload.get("reminder_key")
    if not isinstance(reminder_key, str):
        return None
    try:
        medication_id = UUID(reminder_key.split(":", maxsplit=1)[0])
        return ReminderCaptureContext(
            medication_id=medication_id,
            reminder_key=reminder_key,
        )
    except (ValueError, ValidationError):
        log.warning(
            "patient_reply_reminder_context_invalid",
            treatment_id=str(treatment_id),
            audit_id=str(audit.id),
        )
        return None


async def _reply_already_captured(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    reminder_key: str,
    status: str,
) -> bool:
    result = await session.execute(
        select(AuditLogEntry.id)
        .where(
            AuditLogEntry.event_type == "patient_reply_adherence_captured",
            AuditLogEntry.payload.contains(
                {
                    "treatment_id": str(treatment_id),
                    "reminder_key": reminder_key,
                    "status": status,
                }
            ),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _audit_patient_reply_adherence_capture(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    inbound_message: ConversationMessage,
    context: ReminderCaptureContext,
    status: str,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="patient_reply_adherence_captured",
            resource_type="conversation_message",
            resource_id=inbound_message.id,
            # The patient reply body may contain symptoms or PHI. This marker
            # stores only workflow metadata and a deterministic reminder key.
            payload={
                "treatment_id": str(treatment_id),
                "inbound_message_id": str(inbound_message.id),
                "medication_id": str(context.medication_id),
                "status": status,
                "reminder_key": context.reminder_key,
                "reminder_key_present": True,
            },
        )
    )


def _normalise_message(message: str) -> str:
    return " ".join(message.strip().lower().split())


def _matches_any(message: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, message) for pattern in patterns)

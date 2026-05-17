"""Worker entrypoint for buffered patient-message processing.

Cloud Tasks/Pub/Sub will eventually call this module instead of the current
debug/internal HTTP route. Keeping the orchestration here prevents the route
from becoming the real worker and gives provider adapters one stable function
to invoke.
"""

from dataclasses import dataclass
from uuid import UUID

import structlog
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.patient_reply import PatientReplyDraft, build_patient_reply_agent
from app.agents.patient_reply_classifier import (
    PatientReplyClassification,
    build_patient_reply_classifier_agent,
)
from app.api.schemas import TriageReason
from app.config import Settings
from app.db.models import AuditLogEntry
from app.services import patient_message_buffer
from app.services.conversation_messages import submit_buffered_patient_conversation_turn
from app.services.patient_reply_drafts import (
    TreatmentNotFound as ReplyDraftTreatmentNotFound,
)
from app.services.patient_reply_drafts import (
    draft_patient_reply_for_treatment,
)
from app.services.treatments import get_treatment

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class BufferedPatientMessageWorkerResult:
    processed_count: int
    assistant_message_id: UUID | None
    assistant_status: str | None


async def process_buffered_patient_messages_for_treatment(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    settings: Settings,
) -> BufferedPatientMessageWorkerResult:
    """Process one debounced buffered patient turn for a treatment.

    This is the provider-neutral worker seam. It receives already-buffered
    messages, generates one reply draft, runs the safety pipeline, records the
    resulting assistant message, and marks the inbound rows processed only after
    the handler succeeds.
    """
    assistant_message_id: UUID | None = None
    assistant_status: str | None = None

    async def handle_turn(turn: patient_message_buffer.BufferedPatientTurn) -> None:
        nonlocal assistant_message_id, assistant_status
        draft = await draft_patient_reply_for_treatment(
            session,
            turn.treatment_id,
            patient_message=turn.message_text,
            agent=_build_configured_patient_reply_agent(settings),
        )
        record = await submit_buffered_patient_conversation_turn(
            session,
            treatment_id=turn.treatment_id,
            patient_message=turn.message_text,
            source_message_ids=turn.message_ids,
            assistant_draft=draft.message,
            prescription_context=await _patient_reply_safety_context(
                session,
                turn.treatment_id,
                draft,
            ),
            openai_api_key=settings.openai_api_key,
            safety_provider=settings.safety_provider,
            llama_guard_url=settings.llama_guard_url,
            agentdog_url=settings.agentdog_url,
            safety_provider_api_key=settings.safety_provider_api_key,
            safety_provider_timeout_seconds=settings.safety_provider_timeout_seconds,
            draft_review_reason=_triage_reason_for_patient_reply_draft(draft),
            reply_classifier_agent=_build_configured_patient_reply_classifier_agent(settings),
        )
        assistant_message_id = record.assistant_message.id
        assistant_status = record.assistant_message.status

    result = await patient_message_buffer.process_buffered_patient_turn(
        session,
        treatment_id=treatment_id,
        handle_turn=handle_turn,
    )
    worker_result = BufferedPatientMessageWorkerResult(
        processed_count=result.processed_count,
        assistant_message_id=assistant_message_id,
        assistant_status=assistant_status,
    )
    _audit_worker_run(session, treatment_id=treatment_id, result=worker_result)
    await session.flush()
    log.info(
        "patient_message_buffer_worker_run",
        treatment_id=str(treatment_id),
        processed_count=worker_result.processed_count,
        assistant_message_id=(
            str(worker_result.assistant_message_id)
            if worker_result.assistant_message_id is not None
            else None
        ),
        assistant_status=worker_result.assistant_status,
    )
    return worker_result


def _build_configured_patient_reply_agent(
    settings: Settings,
) -> Agent[None, PatientReplyDraft] | None:
    if settings.openai_api_key is None:
        return None
    provider = OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())
    return build_patient_reply_agent(OpenAIResponsesModel("gpt-5", provider=provider))


def _build_configured_patient_reply_classifier_agent(
    settings: Settings,
) -> Agent[None, PatientReplyClassification] | None:
    if settings.openai_api_key is None:
        return None
    provider = OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())
    return build_patient_reply_classifier_agent(
        OpenAIResponsesModel("gpt-5-nano", provider=provider)
    )


def _triage_reason_for_patient_reply_draft(draft: PatientReplyDraft) -> TriageReason | None:
    """Use the draft agent's validated escalation reason for pharmacist routing."""
    if not draft.requires_pharmacist_review:
        return None
    if draft.escalation_reason == "none":
        return "referee"
    return draft.escalation_reason


async def _patient_reply_safety_context(
    session: AsyncSession,
    treatment_id: UUID,
    draft: PatientReplyDraft,
) -> str:
    detail = await get_treatment(session, treatment_id)
    if detail is None:
        raise ReplyDraftTreatmentNotFound()
    medications = "\n".join(
        (
            f"- {medication.name}; dosage={medication.dosage}; "
            f"frequency={medication.frequency}; duration={medication.duration}; "
            f"objective={medication.objective or 'unavailable'}"
        )
        for medication in detail.medications
    )
    return "\n".join(
        [
            "Treatment context for generated patient-reply draft.",
            f"clinical_objective: {detail.treatment.clinical_objective or 'unavailable'}",
            "medications:",
            medications or "- none",
            (
                "draft_metadata: "
                f"requires_pharmacist_review={draft.requires_pharmacist_review}; "
                f"escalation_reason={draft.escalation_reason}; confidence={draft.confidence}"
            ),
        ]
    )


def _audit_worker_run(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    result: BufferedPatientMessageWorkerResult,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="patient_message_buffer_worker_run",
            resource_type="treatment",
            resource_id=treatment_id,
            # Do not store aggregate patient text or generated reply text here.
            # The audit trail only needs worker outcome metadata.
            payload={
                "treatment_id": str(treatment_id),
                "processed_count": result.processed_count,
                "assistant_message_id": (
                    str(result.assistant_message_id)
                    if result.assistant_message_id is not None
                    else None
                ),
                "assistant_status": result.assistant_status,
            },
        )
    )

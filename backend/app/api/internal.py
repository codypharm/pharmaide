"""Internal maintenance routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
from app.config import Settings, get_settings
from app.db.engine import get_session
from app.db.models import AuditLogEntry
from app.services import (
    dailymed_cache,
    message_delivery,
    monitoring,
    patient_message_buffer,
    task_runner,
)
from app.services.conversation_messages import submit_buffered_patient_conversation_turn
from app.services.patient_reply_drafts import (
    TreatmentNotFound as ReplyDraftTreatmentNotFound,
)
from app.services.patient_reply_drafts import (
    draft_patient_reply_for_treatment,
)
from app.services.treatments import get_treatment

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
SYSTEM_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")

router = APIRouter(prefix="/internal")


class CleanupCheckpointsResponse(BaseModel):
    deleted_count: int
    freed_mb: float


class CleanupDailyMedCacheResponse(BaseModel):
    deleted_count: int
    retention_days: int


class MessageDeliveryRunResponse(BaseModel):
    processed_count: int
    sent_count: int
    failed_count: int


class TreatmentMonitoringRunResponse(BaseModel):
    queued_count: int
    skipped_count: int


class DueMonitoringRunResponse(BaseModel):
    processed_count: int
    queued_count: int
    skipped_count: int


class BufferedPatientTurnProcessResponse(BaseModel):
    processed_count: int
    assistant_message_id: UUID | None = None
    assistant_status: str | None = None


@router.post(
    "/cleanup/checkpoints",
    response_model=CleanupCheckpointsResponse,
)
async def cleanup_checkpoints(
    session: SessionDep,
    settings: SettingsDep,
) -> CleanupCheckpointsResponse:
    result = task_runner.cleanup_checkpoints(settings.checkpoint_db_path)
    session.add(
        AuditLogEntry(
            event_type="checkpoints_cleaned",
            resource_type="system",
            resource_id=SYSTEM_RESOURCE_ID,
            payload={
                "deleted_count": result.deleted_count,
                "freed_mb": result.freed_mb,
                "max_age_days": 7,
            },
        )
    )
    await session.flush()
    return CleanupCheckpointsResponse(
        deleted_count=result.deleted_count,
        freed_mb=result.freed_mb,
    )


@router.post(
    "/cleanup/dailymed-cache",
    response_model=CleanupDailyMedCacheResponse,
)
async def cleanup_dailymed_cache(session: SessionDep) -> CleanupDailyMedCacheResponse:
    deleted_count = await dailymed_cache.cleanup_failed_dailymed_cache(session)
    return CleanupDailyMedCacheResponse(
        deleted_count=deleted_count,
        retention_days=dailymed_cache.DAILYMED_FAILED_CACHE_RETENTION_DAYS,
    )


@router.post(
    "/message-delivery/run-once",
    response_model=MessageDeliveryRunResponse,
)
async def run_message_delivery_once(session: SessionDep) -> MessageDeliveryRunResponse:
    result = await message_delivery.run_message_delivery_once(session)
    return MessageDeliveryRunResponse(
        processed_count=result.processed_count,
        sent_count=result.sent_count,
        failed_count=result.failed_count,
    )


@router.post(
    "/monitoring/run-due",
    response_model=DueMonitoringRunResponse,
)
async def run_due_monitoring(session: SessionDep) -> DueMonitoringRunResponse:
    result = await monitoring.run_due_monitoring(session)
    return DueMonitoringRunResponse(
        processed_count=result.processed_count,
        queued_count=result.queued_count,
        skipped_count=result.skipped_count,
    )


@router.post(
    "/treatments/{treatment_id}/process-buffered-patient-turn",
    response_model=BufferedPatientTurnProcessResponse,
)
async def process_buffered_patient_turn(
    treatment_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
) -> BufferedPatientTurnProcessResponse:
    assistant: dict[str, UUID | str | None] = {
        "message_id": None,
        "status": None,
    }

    async def handle_turn(turn: patient_message_buffer.BufferedPatientTurn) -> None:
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
        assistant["message_id"] = record.assistant_message.id
        assistant["status"] = record.assistant_message.status

    try:
        result = await patient_message_buffer.process_buffered_patient_turn(
            session,
            treatment_id=treatment_id,
            handle_turn=handle_turn,
        )
    except (patient_message_buffer.TreatmentNotFound, ReplyDraftTreatmentNotFound) as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc

    return BufferedPatientTurnProcessResponse(
        processed_count=result.processed_count,
        assistant_message_id=assistant["message_id"],
        assistant_status=assistant["status"],
    )


@router.post(
    "/treatments/{treatment_id}/run-due-monitoring",
    response_model=TreatmentMonitoringRunResponse,
)
async def run_treatment_due_monitoring(
    treatment_id: UUID,
    session: SessionDep,
) -> TreatmentMonitoringRunResponse:
    try:
        result = await monitoring.run_due_monitoring_for_treatment(
            session,
            treatment_id=treatment_id,
        )
    except monitoring.TreatmentNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc
    except monitoring.TreatmentNotActive as exc:
        raise HTTPException(status_code=409, detail={"error": "treatment_not_active"}) from exc

    return TreatmentMonitoringRunResponse(
        queued_count=result.queued_count,
        skipped_count=result.skipped_count,
    )


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

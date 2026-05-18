"""Internal maintenance routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.engine import get_session, get_session_factory
from app.db.models import AuditLogEntry, TreatmentAnalysis
from app.services import (
    dailymed_cache,
    message_delivery,
    monitoring,
    patient_message_buffer,
    patient_message_worker,
    task_runner,
)
from app.services.analysis import analyze_treatment
from app.services.patient_reply_drafts import (
    TreatmentNotFound as ReplyDraftTreatmentNotFound,
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
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


class MessageDeliveryCallbackRequest(BaseModel):
    provider: str
    external_message_id: str
    status: str


class MessageDeliveryCallbackResponse(BaseModel):
    accepted: bool
    reason: str
    message_id: UUID | None = None


class TreatmentMonitoringRunResponse(BaseModel):
    queued_count: int
    skipped_count: int


class DueMonitoringRunResponse(BaseModel):
    processed_count: int
    queued_count: int
    skipped_count: int


class AnalysisRunRequest(BaseModel):
    kb_scope_id: UUID | None = None
    timeout_seconds: int | None = Field(default=None, gt=0, le=300)


class AnalysisRunResponse(BaseModel):
    analysis_id: UUID
    status: str


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
    "/message-delivery/callback",
    response_model=MessageDeliveryCallbackResponse,
)
async def record_message_delivery_callback(
    body: MessageDeliveryCallbackRequest,
    session: SessionDep,
) -> MessageDeliveryCallbackResponse:
    result = await message_delivery.record_delivery_callback(
        session,
        provider=body.provider,
        external_message_id=body.external_message_id,
        status=body.status,
    )
    return MessageDeliveryCallbackResponse(
        accepted=result.accepted,
        reason=result.reason,
        message_id=result.message_id,
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
    "/analyses/{analysis_id}/run",
    response_model=AnalysisRunResponse,
)
async def run_analysis_worker(
    analysis_id: UUID,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
    body: AnalysisRunRequest | None = None,
) -> AnalysisRunResponse:
    """Run one queued analysis job by reopening persisted state from its id."""
    await _ensure_analysis_exists(session_factory, analysis_id)
    run_request = body or AnalysisRunRequest()
    await analyze_treatment(
        session_factory,
        analysis_id,
        run_request.timeout_seconds or settings.analysis_timeout_seconds,
        checkpoint_db_path=settings.checkpoint_db_path,
        rxnorm_base_url=settings.rxnorm_base_url,
        openai_api_key=settings.openai_api_key,
        kb_scope_id=run_request.kb_scope_id,
    )
    status = await _analysis_status(session_factory, analysis_id)
    return AnalysisRunResponse(analysis_id=analysis_id, status=status)


@router.post(
    "/treatments/{treatment_id}/process-buffered-patient-turn",
    response_model=BufferedPatientTurnProcessResponse,
)
async def process_buffered_patient_turn(
    treatment_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
) -> BufferedPatientTurnProcessResponse:
    try:
        result = await patient_message_worker.process_buffered_patient_messages_for_treatment(
            session,
            treatment_id=treatment_id,
            settings=settings,
        )
    except (patient_message_buffer.TreatmentNotFound, ReplyDraftTreatmentNotFound) as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc

    return BufferedPatientTurnProcessResponse(
        processed_count=result.processed_count,
        assistant_message_id=result.assistant_message_id,
        assistant_status=result.assistant_status,
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


async def _ensure_analysis_exists(
    session_factory: async_sessionmaker[AsyncSession],
    analysis_id: UUID,
) -> None:
    status = await _analysis_status(session_factory, analysis_id)
    if status is None:
        raise HTTPException(status_code=404, detail={"error": "analysis_not_found"})


async def _analysis_status(
    session_factory: async_sessionmaker[AsyncSession],
    analysis_id: UUID,
) -> str | None:
    async with session_factory() as session:
        analysis = await session.get(TreatmentAnalysis, analysis_id)
        return analysis.status if analysis is not None else None

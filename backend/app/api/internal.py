"""Internal maintenance routes."""

import base64
import binascii
import json
from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import AliasChoices, BaseModel, Field, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.engine import get_session, get_session_factory
from app.db.models import AuditLogEntry, KnowledgeDocument, TreatmentAnalysis
from app.services import (
    dailymed_cache,
    data_retention,
    internal_worker_auth,
    message_delivery,
    monitoring,
    patient_message_buffer,
    patient_message_worker,
    task_runner,
)
from app.services.analysis import analyze_treatment
from app.services.embeddings import build_embedding_client, embed_texts
from app.services.kb_ingestion import ingest_document
from app.services.knowledge_storage import build_local_knowledge_storage
from app.services.patient_reply_drafts import (
    TreatmentNotFound as ReplyDraftTreatmentNotFound,
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
SYSTEM_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")


async def require_internal_worker_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Require service-to-service auth for internal routes when enabled."""
    settings = request.app.state.settings
    if settings.internal_worker_auth == "disabled":
        return

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"error": "internal_worker_auth_required"})

    token = authorization.removeprefix("Bearer ").strip()
    try:
        internal_worker_auth.verify_internal_oidc_token(
            token,
            audience=settings.internal_worker_audience or "",
        )
    except internal_worker_auth.InternalWorkerAuthError as exc:
        raise HTTPException(
            status_code=401,
            detail={"error": "internal_worker_auth_invalid"},
        ) from exc


async def audit_queue_retry_metadata(
    request: Request,
    session: SessionDep,
) -> None:
    """Audit Cloud Tasks retry metadata without storing worker request bodies."""
    retry_count = _parse_int_header(request, "x-cloudtasks-taskretrycount")
    if retry_count is None or retry_count <= 0:
        return

    session.add(
        AuditLogEntry(
            event_type="queue_task_retry_observed",
            resource_type="queue_task",
            resource_id=SYSTEM_RESOURCE_ID,
            payload={
                "queue_name": request.headers.get("x-cloudtasks-queuename"),
                "task_name": request.headers.get("x-cloudtasks-taskname"),
                "retry_count": retry_count,
                "execution_count": _parse_int_header(
                    request,
                    "x-cloudtasks-taskexecutioncount",
                ),
                "worker_path": request.url.path,
            },
        )
    )
    await session.flush()


router = APIRouter(
    prefix="/internal",
    dependencies=[
        Depends(require_internal_worker_auth),
        Depends(audit_queue_retry_metadata),
    ],
)


class CleanupCheckpointsResponse(BaseModel):
    deleted_count: int
    freed_mb: float


class CleanupDailyMedCacheResponse(BaseModel):
    deleted_count: int
    retention_days: int


class CleanupClosedTreatmentsRequest(BaseModel):
    dry_run: bool = True
    retention_days: int | None = Field(default=None, ge=0, le=3650)
    limit: int = Field(default=100, ge=1, le=1000)


class CleanupClosedTreatmentsResponse(BaseModel):
    dry_run: bool
    retention_days: int
    eligible_treatment_count: int
    deleted_treatment_count: int
    deleted_patient_count: int
    deleted_audit_log_count: int


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


class KnowledgeIngestionRunResponse(BaseModel):
    document_id: UUID
    status: str


class BufferedPatientTurnProcessResponse(BaseModel):
    processed_count: int
    assistant_message_id: UUID | None = None
    assistant_status: str | None = None


class PubSubPushMessage(BaseModel):
    data: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    message_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("messageId", "message_id"),
    )


class PubSubPushRequest(BaseModel):
    message: PubSubPushMessage
    subscription: str | None = None


class SchedulerTickResponse(BaseModel):
    tick_type: str
    result: dict[str, int]


class QueueDeadLetterRequest(BaseModel):
    source: str = Field(min_length=1)
    queue_name: str = Field(min_length=1)
    task_name: str = Field(min_length=1)
    job_name: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    attempt_count: int = Field(ge=0)


class QueueDeadLetterResponse(BaseModel):
    recorded: bool


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
    "/cleanup/closed-treatments",
    response_model=CleanupClosedTreatmentsResponse,
)
async def cleanup_closed_treatments(
    session: SessionDep,
    settings: SettingsDep,
    body: CleanupClosedTreatmentsRequest | None = None,
) -> CleanupClosedTreatmentsResponse:
    request = body or CleanupClosedTreatmentsRequest()
    result = await data_retention.cleanup_closed_treatments(
        session,
        retention_days=(
            request.retention_days
            if request.retention_days is not None
            else settings.data_retention_closed_treatment_days
        ),
        dry_run=request.dry_run,
        limit=request.limit,
    )
    return CleanupClosedTreatmentsResponse(
        dry_run=result.dry_run,
        retention_days=result.retention_days,
        eligible_treatment_count=result.eligible_treatment_count,
        deleted_treatment_count=result.deleted_treatment_count,
        deleted_patient_count=result.deleted_patient_count,
        deleted_audit_log_count=result.deleted_audit_log_count,
    )


@router.post(
    "/message-delivery/run-once",
    response_model=MessageDeliveryRunResponse,
)
async def run_message_delivery_once(
    session: SessionDep,
    settings: SettingsDep,
) -> MessageDeliveryRunResponse:
    result = await message_delivery.run_message_delivery_once(
        session,
        provider=message_delivery.build_delivery_provider(settings),
    )
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
    "/scheduler/pubsub",
    response_model=SchedulerTickResponse,
)
async def run_scheduler_pubsub_tick(
    body: PubSubPushRequest,
    session: SessionDep,
) -> SchedulerTickResponse:
    """Dispatch metadata-only Cloud Scheduler Pub/Sub ticks to internal workers."""
    tick_type = _scheduler_tick_type(body)
    if tick_type == "due_monitoring":
        result = await monitoring.run_due_monitoring(session)
        return SchedulerTickResponse(
            tick_type=tick_type,
            result={
                "processed_count": result.processed_count,
                "queued_count": result.queued_count,
                "skipped_count": result.skipped_count,
            },
        )
    if tick_type == "message_delivery":
        result = await message_delivery.run_message_delivery_once(session)
        return SchedulerTickResponse(
            tick_type=tick_type,
            result={
                "processed_count": result.processed_count,
                "sent_count": result.sent_count,
                "failed_count": result.failed_count,
            },
        )

    raise HTTPException(status_code=400, detail={"error": "unknown_scheduler_tick"})


@router.post(
    "/queue/dead-letter",
    response_model=QueueDeadLetterResponse,
)
async def record_queue_dead_letter(
    body: QueueDeadLetterRequest,
    session: SessionDep,
) -> QueueDeadLetterResponse:
    """Record queue dead-letter metadata without storing clinical payloads."""
    session.add(
        AuditLogEntry(
            event_type="queue_dead_letter_received",
            resource_type="queue_task",
            resource_id=SYSTEM_RESOURCE_ID,
            payload={
                "source": body.source,
                "queue_name": body.queue_name,
                "task_name": body.task_name,
                "job_name": body.job_name,
                "reason": body.reason,
                "attempt_count": body.attempt_count,
            },
        )
    )
    await session.flush()
    return QueueDeadLetterResponse(recorded=True)


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
    "/knowledge/documents/{document_id}/ingest",
    response_model=KnowledgeIngestionRunResponse,
)
async def run_knowledge_ingestion_worker(
    document_id: UUID,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
) -> KnowledgeIngestionRunResponse:
    """Run one queued user-upload ingestion job from persisted metadata."""
    document = await _load_knowledge_document(session_factory, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail={"error": "knowledge_document_not_found"})

    await ingest_document(
        session_factory,
        document_id,
        source=build_local_knowledge_storage(settings.knowledge_upload_dir).source_for(document),
        embedder=_knowledge_embedder(settings.openai_api_key),
    )
    status = await _knowledge_document_status(session_factory, document_id)
    return KnowledgeIngestionRunResponse(document_id=document_id, status=status)


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


async def _load_knowledge_document(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
) -> KnowledgeDocument | None:
    async with session_factory() as session:
        return await session.get(KnowledgeDocument, document_id)


async def _knowledge_document_status(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
) -> str:
    document = await _load_knowledge_document(session_factory, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail={"error": "knowledge_document_not_found"})
    return document.status


def _knowledge_embedder(openai_api_key: SecretStr | None):
    async def embed(texts: Sequence[str]) -> list[list[float]]:
        client = build_embedding_client(openai_api_key)
        try:
            return await embed_texts(texts, client=client)
        finally:
            await client.close()

    return embed


def _scheduler_tick_type(body: PubSubPushRequest) -> str | None:
    """Read tick type from attributes first, then from base64 JSON data."""
    attribute_tick = body.message.attributes.get("tick_type")
    if attribute_tick:
        return attribute_tick

    payload = _decode_pubsub_json(body.message.data)
    tick_type = payload.get("tick_type")
    return tick_type if isinstance(tick_type, str) else None


def _decode_pubsub_json(data: str | None) -> dict[str, object]:
    if not data:
        return {}
    try:
        decoded = base64.b64decode(data, validate=True).decode("utf-8")
        payload = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_pubsub_message"}) from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={"error": "invalid_pubsub_message"})
    return payload


def _parse_int_header(request: Request, name: str) -> int | None:
    value = request.headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None

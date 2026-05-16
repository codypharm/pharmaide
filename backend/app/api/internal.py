"""Internal maintenance routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.engine import get_session
from app.db.models import AuditLogEntry
from app.services import dailymed_cache, message_delivery, task_runner

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

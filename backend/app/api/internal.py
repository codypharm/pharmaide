"""Internal maintenance routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.engine import get_session
from app.db.models import AuditLogEntry
from app.services import task_runner

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
SYSTEM_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")

router = APIRouter(prefix="/internal")


class CleanupCheckpointsResponse(BaseModel):
    deleted_count: int
    freed_mb: float


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

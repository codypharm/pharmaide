"""System audit route handlers."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AuditLogEntryList
from app.db.engine import get_session
from app.services.audits import list_audit_log_entries

SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix="/audits")


@router.get("", response_model=AuditLogEntryList)
async def get_audit_log_entries(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    event_type: Annotated[str | None, Query(min_length=1)] = None,
    resource_type: Annotated[str | None, Query(min_length=1)] = None,
    actor_id: UUID | None = None,
) -> AuditLogEntryList:
    entries = await list_audit_log_entries(
        session,
        limit=limit,
        offset=offset,
        event_type=event_type,
        resource_type=resource_type,
        actor_id=actor_id,
    )
    return AuditLogEntryList(items=entries)

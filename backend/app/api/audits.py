"""System audit route handlers."""

from typing import Annotated

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
) -> AuditLogEntryList:
    entries = await list_audit_log_entries(session, limit=limit, offset=offset)
    return AuditLogEntryList(items=entries)

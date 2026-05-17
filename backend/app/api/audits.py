"""System audit route handlers."""

import csv
import json
from io import StringIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AuditLogEntryList
from app.db.engine import get_session
from app.db.models import AuditLogEntry
from app.services.audits import list_audit_log_entries

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AUDIT_EXPORT_FILENAME = "pharmaide-audit-trail.csv"

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


@router.get("/export.csv")
async def export_audit_log_entries(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
    event_type: Annotated[str | None, Query(min_length=1)] = None,
    resource_type: Annotated[str | None, Query(min_length=1)] = None,
    actor_id: UUID | None = None,
) -> Response:
    entries = await list_audit_log_entries(
        session,
        limit=limit,
        offset=offset,
        event_type=event_type,
        resource_type=resource_type,
        actor_id=actor_id,
    )
    return Response(
        content=_audit_entries_csv(entries),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{AUDIT_EXPORT_FILENAME}"'},
    )


def _audit_entries_csv(entries: list[AuditLogEntry]) -> str:
    """Serialize audit metadata only; PHI-bearing tables are not joined here."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "created_at",
            "actor_id",
            "event_type",
            "resource_type",
            "resource_id",
            "payload",
        ],
    )
    writer.writeheader()
    for entry in entries:
        writer.writerow(
            {
                "id": str(entry.id),
                "created_at": entry.created_at.isoformat(),
                "actor_id": "" if entry.actor_id is None else str(entry.actor_id),
                "event_type": entry.event_type,
                "resource_type": entry.resource_type,
                "resource_id": str(entry.resource_id),
                "payload": json.dumps(entry.payload, sort_keys=True, separators=(",", ":")),
            }
        )
    return output.getvalue()

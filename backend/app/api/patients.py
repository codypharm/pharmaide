"""Read-only patient lookup routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PatientList
from app.db.engine import get_session
from app.services.patients import search_patients

SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter()


@router.get("/patients", response_model=PatientList)
async def list_patients_route(
    session: SessionDep,
    query: Annotated[str, Query(min_length=1, max_length=128)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PatientList:
    normalized_query = query.strip()
    if not normalized_query:
        raise HTTPException(status_code=422, detail={"error": "blank_query"})
    return await search_patients(
        session,
        query=normalized_query,
        limit=limit,
        offset=offset,
    )

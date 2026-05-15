"""Pharmacist triage queue route handlers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import TriageItemList
from app.db.engine import get_session
from app.services.triage import list_triage_items

SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix="/triage")


@router.get(
    "/items",
    response_model=TriageItemList,
)
async def get_triage_items(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TriageItemList:
    return await list_triage_items(session, limit=limit, offset=offset)

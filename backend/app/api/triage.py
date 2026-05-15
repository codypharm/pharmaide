"""Pharmacist triage queue route handlers."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import TriageItemList, TriageItemUpdate, TriageItemView
from app.db.engine import get_session
from app.services.triage import (
    InvalidTriageTransition,
    TriageItemNotFound,
    list_triage_items,
    update_triage_item_status,
)

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


@router.patch(
    "/items/{item_id}",
    response_model=TriageItemView,
)
async def patch_triage_item(
    item_id: UUID,
    body: TriageItemUpdate,
    session: SessionDep,
) -> TriageItemView:
    try:
        return await update_triage_item_status(session, item_id, status=body.status)
    except TriageItemNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "triage_item_not_found"}) from exc
    except InvalidTriageTransition as exc:
        raise HTTPException(status_code=409, detail={"error": "invalid_triage_transition"}) from exc

"""Pharmacist triage queue route handlers."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    TriageApprovalView,
    TriageDeliveryView,
    TriageItemList,
    TriageItemUpdate,
    TriageItemView,
    TriageRejectionView,
)
from app.auth import CurrentActor, get_current_actor
from app.db.engine import get_session
from app.services.triage import (
    InvalidTriageTransition,
    TriageDraftNotApprovable,
    TriageDraftNotQueueable,
    TriageDraftNotRejectable,
    TriageItemNotFound,
    approve_triage_item_draft,
    list_triage_items,
    queue_triage_item_delivery,
    reject_triage_item_draft,
    update_triage_item_status,
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ActorDep = Annotated[CurrentActor, Depends(get_current_actor)]

router = APIRouter(prefix="/triage", dependencies=[Depends(get_current_actor)])


@router.get(
    "/items",
    response_model=TriageItemList,
)
async def get_triage_items(
    session: SessionDep,
    actor: ActorDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TriageItemList:
    return await list_triage_items(
        session, limit=limit, offset=offset, scope_id=actor.kb_scope_id
    )


@router.patch(
    "/items/{item_id}",
    response_model=TriageItemView,
)
async def patch_triage_item(
    item_id: UUID,
    body: TriageItemUpdate,
    session: SessionDep,
    actor: ActorDep,
) -> TriageItemView:
    try:
        return await update_triage_item_status(
            session, item_id, status=body.status, scope_id=actor.kb_scope_id
        )
    except TriageItemNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "triage_item_not_found"}) from exc
    except InvalidTriageTransition as exc:
        raise HTTPException(status_code=409, detail={"error": "invalid_triage_transition"}) from exc


@router.post(
    "/items/{item_id}/approve",
    response_model=TriageApprovalView,
)
async def approve_triage_item(
    item_id: UUID,
    session: SessionDep,
    actor: ActorDep,
) -> TriageApprovalView:
    try:
        return await approve_triage_item_draft(session, item_id, scope_id=actor.kb_scope_id)
    except TriageItemNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "triage_item_not_found"}) from exc
    except InvalidTriageTransition as exc:
        raise HTTPException(status_code=409, detail={"error": "invalid_triage_transition"}) from exc
    except TriageDraftNotApprovable as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "triage_draft_not_approvable"},
        ) from exc


@router.post(
    "/items/{item_id}/reject",
    response_model=TriageRejectionView,
)
async def reject_triage_item(
    item_id: UUID,
    session: SessionDep,
    actor: ActorDep,
) -> TriageRejectionView:
    try:
        return await reject_triage_item_draft(session, item_id, scope_id=actor.kb_scope_id)
    except TriageItemNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "triage_item_not_found"}) from exc
    except InvalidTriageTransition as exc:
        raise HTTPException(status_code=409, detail={"error": "invalid_triage_transition"}) from exc
    except TriageDraftNotRejectable as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "triage_draft_not_rejectable"},
        ) from exc


@router.post(
    "/items/{item_id}/queue-delivery",
    response_model=TriageDeliveryView,
)
async def queue_triage_item_for_delivery(
    item_id: UUID,
    session: SessionDep,
    actor: ActorDep,
) -> TriageDeliveryView:
    try:
        return await queue_triage_item_delivery(session, item_id, scope_id=actor.kb_scope_id)
    except TriageItemNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "triage_item_not_found"}) from exc
    except TriageDraftNotQueueable as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "triage_draft_not_queueable"},
        ) from exc

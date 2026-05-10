"""POST /treatments and GET /treatments/:id route handlers.

Thin translators between the wire and the service layer. No DB access
here — the service owns the transaction; this module owns HTTP semantics
(status codes, error envelopes, dependency wiring).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    CreateTreatmentRequest,
    CreateTreatmentResponse,
    TreatmentDetail,
)
from app.db.engine import get_session
from app.services.treatments import MRNConflict, create_treatment, get_treatment

# FastAPI's modern dependency form. Prevents the lint trap where
# Depends() looks like a side-effecting default value.
SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter()


@router.post(
    "/treatments",
    status_code=201,
    response_model=CreateTreatmentResponse,
)
async def post_treatment(
    body: CreateTreatmentRequest, session: SessionDep
) -> CreateTreatmentResponse:
    try:
        return await create_treatment(session, body)
    except MRNConflict as exc:
        raise HTTPException(status_code=409, detail={"error": "mrn_already_exists"}) from exc


@router.get(
    "/treatments/{treatment_id}",
    response_model=TreatmentDetail,
)
async def get_treatment_by_id(treatment_id: UUID, session: SessionDep) -> TreatmentDetail:
    detail = await get_treatment(session, treatment_id)
    if detail is None:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"})
    return detail

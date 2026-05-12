"""POST /treatments and GET /treatments/:id route handlers.

Thin translators between the wire and the service layer. No DB access
here — the service owns the transaction; this module owns HTTP semantics
(status codes, error envelopes, dependency wiring).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas import (
    AnalyzeTreatmentResponse,
    CreateTreatmentRequest,
    CreateTreatmentResponse,
    TreatmentAnalysisView,
    TreatmentDetail,
    TreatmentList,
)
from app.config import Settings, get_settings
from app.db.engine import get_session, get_session_factory
from app.services import task_runner
from app.services.analysis import (
    AnalysisInProgress,
    analyze_treatment,
    create_pending_analysis,
    get_latest_analysis,
)
from app.services.treatments import (
    MRNConflict,
    create_treatment,
    get_treatment,
    list_treatments,
    treatment_exists,
)

# FastAPI's modern dependency form. Prevents the lint trap where
# Depends() looks like a side-effecting default value.
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

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
    "/treatments",
    response_model=TreatmentList,
)
async def list_treatments_route(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TreatmentList:
    return await list_treatments(session, limit=limit, offset=offset)


@router.get(
    "/treatments/{treatment_id}",
    response_model=TreatmentDetail,
)
async def get_treatment_by_id(treatment_id: UUID, session: SessionDep) -> TreatmentDetail:
    detail = await get_treatment(session, treatment_id)
    if detail is None:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"})
    return detail


@router.post(
    "/treatments/{treatment_id}/analyze",
    status_code=202,
    response_model=AnalyzeTreatmentResponse,
)
async def post_treatment_analysis(
    treatment_id: UUID,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
    timeout: Annotated[int | None, Query(gt=0, le=300)] = None,
) -> AnalyzeTreatmentResponse:
    try:
        # Commit the pending row before scheduling. Otherwise the background
        # task can race the request transaction and fail to see its work.
        async with session_factory() as session, session.begin():
            if not await treatment_exists(session, treatment_id):
                raise HTTPException(status_code=404, detail={"error": "treatment_not_found"})
            analysis_id = await create_pending_analysis(session, treatment_id)
    except AnalysisInProgress as exc:
        raise HTTPException(status_code=409, detail={"error": "analysis_in_progress"}) from exc
    timeout_seconds = timeout if timeout is not None else settings.analysis_timeout_seconds
    task_runner.schedule(analyze_treatment, session_factory, analysis_id, timeout_seconds)
    return AnalyzeTreatmentResponse(analysis_id=analysis_id)


@router.get(
    "/treatments/{treatment_id}/analysis",
    response_model=TreatmentAnalysisView,
)
async def get_treatment_analysis(
    treatment_id: UUID, session: SessionDep
) -> TreatmentAnalysisView | Response:
    if not await treatment_exists(session, treatment_id):
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"})

    analysis = await get_latest_analysis(session, treatment_id)
    if analysis is None:
        return Response(status_code=204)
    return TreatmentAnalysisView.model_validate(analysis)

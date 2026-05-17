"""POST /treatments and GET /treatments/:id route handlers.

Thin translators between the wire and the service layer. No DB access
here — the service owns the transaction; this module owns HTTP semantics
(status codes, error envelopes, dependency wiring).
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.patient_reply import PatientReplyDraft, build_patient_reply_agent
from app.agents.patient_reply_classifier import (
    PatientReplyClassification,
    build_patient_reply_classifier_agent,
)
from app.api.schemas import (
    AdherenceEventCreate,
    AdherenceEventList,
    AdherenceEventView,
    AnalyzeTreatmentResponse,
    ConversationMessageList,
    ConversationMessageView,
    ConversationTurnCreate,
    ConversationTurnView,
    CreateTreatmentRequest,
    CreateTreatmentResponse,
    PatientCheckInCreate,
    PatientCheckInList,
    PatientCheckInView,
    PatientConversationMessageCreate,
    PatientReplyDraftCreate,
    PharmacistConversationMessageCreate,
    TreatmentAnalysisView,
    TreatmentChatResponseModeUpdate,
    TreatmentClinicalObjectiveUpdate,
    TreatmentDetail,
    TreatmentList,
    TreatmentView,
    TriageReason,
)
from app.config import Settings, get_settings
from app.db.engine import get_session, get_session_factory
from app.services import task_runner
from app.services.adherence_events import (
    MedicationNotFound as AdherenceMedicationNotFound,
)
from app.services.adherence_events import (
    TreatmentNotFound as AdherenceTreatmentNotFound,
)
from app.services.adherence_events import (
    create_adherence_event,
    list_adherence_events,
)
from app.services.analysis import (
    AnalysisInProgress,
    analyze_treatment,
    create_pending_analysis,
    get_latest_analysis,
    get_latest_completed_analysis,
    mark_analysis_failed,
)
from app.services.conversation_messages import (
    InvalidDeliveryRetry,
    list_conversation_messages,
    record_patient_conversation_message,
    record_pharmacist_conversation_message,
    retry_failed_conversation_message_delivery,
    submit_patient_conversation_turn,
    submit_pharmacist_takeover_holding_turn,
)
from app.services.conversation_messages import (
    TreatmentNotFound as ConversationTreatmentNotFound,
)
from app.services.course_completion_report import (
    CourseCompletionReport,
    audit_course_completion_report_viewed,
    build_course_completion_report,
)
from app.services.course_completion_report import (
    TreatmentNotFound as CompletionReportTreatmentNotFound,
)
from app.services.patient_checkins import (
    TreatmentNotFound as CheckInTreatmentNotFound,
)
from app.services.patient_checkins import (
    create_patient_check_in,
    list_patient_check_ins,
)
from app.services.patient_reply_drafts import (
    TreatmentNotFound as ReplyDraftTreatmentNotFound,
)
from app.services.patient_reply_drafts import (
    build_pharmacist_takeover_holding_draft,
    draft_patient_reply_for_treatment,
)
from app.services.treatments import (
    AnalysisNotCompleted,
    MRNConflict,
    TreatmentNotCompleted,
    archive_treatment,
    create_treatment,
    get_treatment,
    list_treatments,
    start_treatment_cycle,
    treatment_exists,
    update_chat_response_mode,
    update_clinical_objective,
)
from app.services.treatments import (
    TreatmentNotFound as TreatmentCommandNotFound,
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
    body: CreateTreatmentRequest,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
    user_id: Annotated[str, Header(alias="X-Pharmaide-User-Id", min_length=1)] = "anonymous",
) -> CreateTreatmentResponse:
    try:
        # Create the treatment and reserve its first analysis in one request
        # transaction so every client gets the same startup behavior.
        async with session_factory() as session, session.begin():
            created = await create_treatment(session, body)
            analysis_id = await create_pending_analysis(session, created.treatment_id)
    except MRNConflict as exc:
        raise HTTPException(status_code=409, detail={"error": "mrn_already_exists"}) from exc
    timeout_seconds = settings.analysis_timeout_seconds
    try:
        _schedule_analysis(
            session_factory,
            settings,
            analysis_id,
            timeout_seconds=timeout_seconds,
            user_id=user_id,
        )
    except task_runner.RateLimitExceeded:
        await mark_analysis_failed(session_factory, analysis_id, "analysis_rate_limited")

    return created.model_copy(update={"analysis_id": analysis_id})


@router.get(
    "/treatments",
    response_model=TreatmentList,
)
async def list_treatments_route(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: Annotated[Literal["pending", "active", "completed"] | None, Query()] = None,
    archived: Annotated[bool | None, Query()] = None,
) -> TreatmentList:
    return await list_treatments(
        session,
        limit=limit,
        offset=offset,
        status=status,
        archived=archived,
    )


@router.get(
    "/treatments/{treatment_id}",
    response_model=TreatmentDetail,
)
async def get_treatment_by_id(treatment_id: UUID, session: SessionDep) -> TreatmentDetail:
    detail = await get_treatment(session, treatment_id)
    if detail is None:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"})
    return detail


@router.get(
    "/treatments/{treatment_id}/completion-report",
    response_model=CourseCompletionReport,
)
async def get_treatment_completion_report(
    treatment_id: UUID,
    session: SessionDep,
) -> CourseCompletionReport:
    try:
        report = await build_course_completion_report(session, treatment_id=treatment_id)
    except CompletionReportTreatmentNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc

    # The builder is reusable for deterministic counts, but this HTTP endpoint
    # only exposes finalized course reports after completion.
    if report.status != "completed":
        raise HTTPException(status_code=409, detail={"error": "treatment_not_completed"})
    audit_course_completion_report_viewed(session, report)
    return report


@router.post(
    "/treatments/{treatment_id}/chat-response-mode",
    response_model=TreatmentView,
)
async def post_treatment_chat_response_mode(
    treatment_id: UUID,
    body: TreatmentChatResponseModeUpdate,
    session_factory: SessionFactoryDep,
) -> TreatmentView:
    try:
        async with session_factory() as session, session.begin():
            return await update_chat_response_mode(
                session,
                treatment_id,
                chat_response_mode=body.chat_response_mode,
            )
    except TreatmentCommandNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc


@router.post(
    "/treatments/{treatment_id}/start-cycle",
    response_model=TreatmentView,
)
async def post_treatment_start_cycle(
    treatment_id: UUID,
    session: SessionDep,
) -> TreatmentView:
    try:
        return await start_treatment_cycle(session, treatment_id)
    except TreatmentCommandNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc
    except AnalysisNotCompleted as exc:
        raise HTTPException(status_code=409, detail={"error": "analysis_not_completed"}) from exc


@router.post(
    "/treatments/{treatment_id}/archive",
    response_model=TreatmentView,
)
async def post_treatment_archive(
    treatment_id: UUID,
    session: SessionDep,
) -> TreatmentView:
    try:
        return await archive_treatment(session, treatment_id)
    except TreatmentCommandNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc
    except TreatmentNotCompleted as exc:
        raise HTTPException(status_code=409, detail={"error": "treatment_not_completed"}) from exc


@router.post(
    "/treatments/{treatment_id}/clinical-objective",
    response_model=TreatmentView,
)
async def post_treatment_clinical_objective(
    treatment_id: UUID,
    body: TreatmentClinicalObjectiveUpdate,
    session_factory: SessionFactoryDep,
) -> TreatmentView:
    try:
        async with session_factory() as session, session.begin():
            return await update_clinical_objective(
                session,
                treatment_id,
                clinical_objective=body.clinical_objective,
            )
    except TreatmentCommandNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc


@router.post(
    "/treatments/{treatment_id}/check-ins",
    status_code=201,
    response_model=PatientCheckInView,
)
async def post_patient_check_in(
    treatment_id: UUID,
    body: PatientCheckInCreate,
    session_factory: SessionFactoryDep,
) -> PatientCheckInView:
    try:
        async with session_factory() as session, session.begin():
            return await create_patient_check_in(session, treatment_id, body)
    except CheckInTreatmentNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc


@router.get(
    "/treatments/{treatment_id}/check-ins",
    response_model=PatientCheckInList,
)
async def get_patient_check_ins(
    treatment_id: UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PatientCheckInList:
    try:
        return await list_patient_check_ins(session, treatment_id, limit=limit, offset=offset)
    except CheckInTreatmentNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc


@router.post(
    "/treatments/{treatment_id}/adherence-events",
    status_code=201,
    response_model=AdherenceEventView,
)
async def post_adherence_event(
    treatment_id: UUID,
    body: AdherenceEventCreate,
    session_factory: SessionFactoryDep,
) -> AdherenceEventView:
    try:
        async with session_factory() as session, session.begin():
            return await create_adherence_event(session, treatment_id, body)
    except AdherenceTreatmentNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc
    except AdherenceMedicationNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "medication_not_found"}) from exc


@router.get(
    "/treatments/{treatment_id}/adherence-events",
    response_model=AdherenceEventList,
)
async def get_adherence_events(
    treatment_id: UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdherenceEventList:
    try:
        return await list_adherence_events(session, treatment_id, limit=limit, offset=offset)
    except AdherenceTreatmentNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc


@router.post(
    "/treatments/{treatment_id}/conversation-turns",
    status_code=201,
    response_model=ConversationTurnView,
)
async def post_conversation_turn(
    treatment_id: UUID,
    body: ConversationTurnCreate,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
) -> ConversationTurnView:
    try:
        async with session_factory() as session, session.begin():
            return await submit_patient_conversation_turn(
                session,
                treatment_id=treatment_id,
                patient_message=body.patient_message,
                assistant_draft=body.assistant_draft,
                prescription_context=body.prescription_context,
                openai_api_key=settings.openai_api_key,
                safety_provider=settings.safety_provider,
                llama_guard_url=settings.llama_guard_url,
                agentdog_url=settings.agentdog_url,
                safety_provider_api_key=settings.safety_provider_api_key,
                safety_provider_timeout_seconds=settings.safety_provider_timeout_seconds,
                reply_classifier_agent=_build_configured_patient_reply_classifier_agent(settings),
            )
    except ConversationTreatmentNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc


@router.post(
    "/treatments/{treatment_id}/patient-messages",
    status_code=201,
    response_model=ConversationMessageView,
)
async def post_patient_message(
    treatment_id: UUID,
    body: PatientConversationMessageCreate,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
) -> ConversationMessageView:
    try:
        async with session_factory() as session, session.begin():
            return await record_patient_conversation_message(
                session,
                treatment_id=treatment_id,
                message=body.message,
                reply_classifier_agent=_build_configured_patient_reply_classifier_agent(settings),
            )
    except ConversationTreatmentNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc


@router.post(
    "/treatments/{treatment_id}/pharmacist-messages",
    status_code=201,
    response_model=ConversationMessageView,
)
async def post_pharmacist_message(
    treatment_id: UUID,
    body: PharmacistConversationMessageCreate,
    session_factory: SessionFactoryDep,
) -> ConversationMessageView:
    try:
        async with session_factory() as session, session.begin():
            return await record_pharmacist_conversation_message(
                session,
                treatment_id=treatment_id,
                message=body.message,
            )
    except ConversationTreatmentNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc


@router.post(
    "/treatments/{treatment_id}/conversation-messages/{message_id}/retry-delivery",
    response_model=ConversationMessageView,
)
async def post_retry_conversation_message_delivery(
    treatment_id: UUID,
    message_id: UUID,
    session_factory: SessionFactoryDep,
) -> ConversationMessageView:
    try:
        async with session_factory() as session, session.begin():
            return await retry_failed_conversation_message_delivery(
                session,
                treatment_id=treatment_id,
                message_id=message_id,
            )
    except ConversationTreatmentNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "conversation_message_not_found"},
        ) from exc
    except InvalidDeliveryRetry as exc:
        raise HTTPException(status_code=409, detail={"error": "message_not_retryable"}) from exc


@router.get(
    "/treatments/{treatment_id}/conversation-messages",
    response_model=ConversationMessageList,
)
async def get_conversation_messages(
    treatment_id: UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationMessageList:
    try:
        return await list_conversation_messages(
            session,
            treatment_id,
            limit=limit,
            offset=offset,
        )
    except ConversationTreatmentNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc


@router.post(
    "/treatments/{treatment_id}/patient-reply-drafts",
    status_code=201,
    response_model=ConversationTurnView,
)
async def post_patient_reply_draft(
    treatment_id: UUID,
    body: PatientReplyDraftCreate,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
) -> ConversationTurnView:
    try:
        async with session_factory() as session, session.begin():
            detail = await get_treatment(session, treatment_id)
            if detail is None:
                raise ReplyDraftTreatmentNotFound()
            if detail.treatment.chat_response_mode == "pharmacist_takeover":
                draft = build_pharmacist_takeover_holding_draft()
                return await submit_pharmacist_takeover_holding_turn(
                    session,
                    treatment_id=treatment_id,
                    patient_message=body.patient_message,
                    assistant_draft=draft.message,
                    reply_classifier_agent=_build_configured_patient_reply_classifier_agent(
                        settings
                    ),
                )

            draft = await draft_patient_reply_for_treatment(
                session,
                treatment_id,
                patient_message=body.patient_message,
                agent=_build_configured_patient_reply_agent(settings),
            )
            return await submit_patient_conversation_turn(
                session,
                treatment_id=treatment_id,
                patient_message=body.patient_message,
                assistant_draft=draft.message,
                prescription_context=await _patient_reply_safety_context(
                    session,
                    treatment_id,
                    draft,
                ),
                openai_api_key=settings.openai_api_key,
                safety_provider=settings.safety_provider,
                llama_guard_url=settings.llama_guard_url,
                agentdog_url=settings.agentdog_url,
                safety_provider_api_key=settings.safety_provider_api_key,
                safety_provider_timeout_seconds=settings.safety_provider_timeout_seconds,
                draft_review_reason=_triage_reason_for_patient_reply_draft(draft),
                reply_classifier_agent=_build_configured_patient_reply_classifier_agent(settings),
            )
    except (ConversationTreatmentNotFound, ReplyDraftTreatmentNotFound) as exc:
        raise HTTPException(status_code=404, detail={"error": "treatment_not_found"}) from exc


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
    force: bool = False,
    user_id: Annotated[str, Header(alias="X-Pharmaide-User-Id", min_length=1)] = "anonymous",
) -> AnalyzeTreatmentResponse:
    try:
        # Commit the pending row before scheduling. Otherwise the background
        # task can race the request transaction and fail to see its work.
        async with session_factory() as session, session.begin():
            if not await treatment_exists(session, treatment_id):
                raise HTTPException(status_code=404, detail={"error": "treatment_not_found"})
            analysis_id = await create_pending_analysis(session, treatment_id, force=force)
    except AnalysisInProgress as exc:
        raise HTTPException(status_code=409, detail={"error": "analysis_in_progress"}) from exc
    timeout_seconds = timeout if timeout is not None else settings.analysis_timeout_seconds
    try:
        _schedule_analysis(
            session_factory,
            settings,
            analysis_id,
            timeout_seconds=timeout_seconds,
            user_id=user_id,
        )
    except task_runner.RateLimitExceeded as exc:
        await mark_analysis_failed(session_factory, analysis_id, "analysis_rate_limited")
        raise HTTPException(
            status_code=429,
            detail={"error": "analysis_rate_limited"},
            headers={"Retry-After": "30"},
        ) from exc
    return AnalyzeTreatmentResponse(analysis_id=analysis_id)


def _build_configured_patient_reply_agent(
    settings: Settings,
) -> Agent[None, PatientReplyDraft] | None:
    if settings.openai_api_key is None:
        return None
    provider = OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())
    return build_patient_reply_agent(OpenAIResponsesModel("gpt-5", provider=provider))


def _build_configured_patient_reply_classifier_agent(
    settings: Settings,
) -> Agent[None, PatientReplyClassification] | None:
    if settings.openai_api_key is None:
        return None
    provider = OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())
    return build_patient_reply_classifier_agent(
        OpenAIResponsesModel("gpt-5-nano", provider=provider)
    )


def _triage_reason_for_patient_reply_draft(draft: PatientReplyDraft) -> TriageReason | None:
    """Use the draft agent's validated escalation reason for pharmacist routing."""
    if not draft.requires_pharmacist_review:
        return None
    if draft.escalation_reason == "none":
        return "referee"
    return draft.escalation_reason


async def _patient_reply_safety_context(
    session: AsyncSession,
    treatment_id: UUID,
    draft: PatientReplyDraft,
) -> str:
    detail = await get_treatment(session, treatment_id)
    if detail is None:
        raise ReplyDraftTreatmentNotFound()
    medications = "\n".join(
        (
            f"- {medication.name}; dosage={medication.dosage}; "
            f"frequency={medication.frequency}; duration={medication.duration}; "
            f"objective={medication.objective or 'unavailable'}"
        )
        for medication in detail.medications
    )
    return "\n".join(
        [
            "Treatment context for generated patient-reply draft.",
            f"clinical_objective: {detail.treatment.clinical_objective or 'unavailable'}",
            "medications:",
            medications or "- none",
            (
                "draft_metadata: "
                f"requires_pharmacist_review={draft.requires_pharmacist_review}; "
                f"escalation_reason={draft.escalation_reason}; confidence={draft.confidence}"
            ),
        ]
    )


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

    response = TreatmentAnalysisView.model_validate(analysis)
    completed = await get_latest_completed_analysis(session, treatment_id)
    if completed is not None and completed.id != analysis.id:
        response.last_completed = TreatmentAnalysisView.model_validate(completed)
    return response


def _parse_optional_uuid(value: str) -> UUID | None:
    """Pre-auth user ids may be labels; only UUID actor ids can scope KB rows."""
    try:
        return UUID(value)
    except ValueError:
        return None


def _schedule_analysis(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    analysis_id: UUID,
    *,
    timeout_seconds: int,
    user_id: str,
) -> None:
    """Schedule analysis with the same runtime options for create and rerun."""
    task_runner.schedule(
        analyze_treatment,
        session_factory,
        analysis_id,
        timeout_seconds,
        checkpoint_db_path=settings.checkpoint_db_path,
        rxnorm_base_url=settings.rxnorm_base_url,
        openai_api_key=settings.openai_api_key,
        kb_scope_id=_parse_optional_uuid(user_id),
        user_id=user_id,
        max_concurrent_per_user=settings.max_concurrent_analyses_per_user,
    )

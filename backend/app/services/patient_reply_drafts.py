"""Build patient-reply draft context from persisted treatment data."""

from uuid import UUID

import structlog
from pydantic_ai import Agent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.patient_reply import (
    ConversationMessageContext,
    InteractionEvidenceContext,
    MedicationContext,
    PatientReplyContext,
    PatientReplyDraft,
    draft_patient_reply,
)
from app.db.models import ConversationMessage, Treatment, TreatmentAnalysis
from app.services.patient_interaction_evidence import (
    InteractionEvidenceRetriever,
    PatientInteractionEvidence,
    lookup_patient_interaction_evidence,
)

log = structlog.get_logger(__name__)


class TreatmentNotFound(Exception):
    """Raised when a patient-reply draft references a missing treatment."""


async def draft_patient_reply_for_treatment(
    session: AsyncSession,
    treatment_id: UUID,
    *,
    patient_message: str,
    agent: Agent[None, PatientReplyDraft] | None = None,
    interaction_evidence_retriever: InteractionEvidenceRetriever | None = None,
    recent_message_limit: int = 10,
) -> PatientReplyDraft:
    """Generate a typed draft using persisted treatment and chat context."""
    treatment = await _load_treatment(session, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()
    if treatment.chat_response_mode == "pharmacist_takeover":
        draft = build_pharmacist_takeover_holding_draft()
        log.info(
            "patient_reply_holding_draft_generated",
            treatment_id=str(treatment_id),
            chat_response_mode=treatment.chat_response_mode,
            automation_mode=treatment.automation_mode,
        )
        return draft

    recent_messages = await _recent_message_context(
        session,
        treatment_id,
        limit=recent_message_limit,
    )
    latest_summary = await _latest_analysis_summary(session, treatment_id)
    interaction_evidence = await lookup_patient_interaction_evidence(
        patient_message=patient_message,
        medication_names=[medication.name for medication in treatment.medications],
        treatment_id=treatment_id,
        retriever=interaction_evidence_retriever,
    )
    context = PatientReplyContext(
        treatment_id=treatment.id,
        patient_message=patient_message,
        clinical_objective=treatment.clinical_objective,
        medications=[
            MedicationContext(
                name=medication.name,
                dosage=medication.dosage,
                frequency=medication.frequency,
                duration=medication.duration,
                objective=medication.objective,
            )
            for medication in treatment.medications
        ],
        recent_messages=recent_messages,
        latest_analysis_summary=latest_summary,
        interaction_question_detected=interaction_evidence.is_interaction_question,
        interaction_evidence=[
            InteractionEvidenceContext(
                source_type=citation.source_type,
                document_title=citation.document_title,
                source_uri=citation.source_uri,
                excerpt=citation.text,
                score=citation.score,
            )
            for citation in interaction_evidence.citations
        ],
    )
    draft = await draft_patient_reply(context, agent=agent)
    draft = _hold_ungrounded_interaction_draft(draft, interaction_evidence)
    log.info(
        "patient_reply_draft_generated",
        treatment_id=str(treatment_id),
        medication_count=len(context.medications),
        recent_message_count=len(recent_messages),
        latest_analysis_summary_present=latest_summary is not None,
        interaction_question_detected=interaction_evidence.is_interaction_question,
        interaction_evidence_count=len(interaction_evidence.citations),
        requires_pharmacist_review=draft.requires_pharmacist_review,
        escalation_reason=draft.escalation_reason,
        confidence=draft.confidence,
    )
    return draft


def build_pharmacist_takeover_holding_draft() -> PatientReplyDraft:
    """Return a validated holding response while the pharmacist owns the thread."""
    return PatientReplyDraft(
        message=(
            "Your pharmacist is reviewing this. I will let you know when there is an "
            "update. Please continue following your current instructions unless your "
            "pharmacist tells you otherwise."
        ),
        requires_pharmacist_review=False,
        escalation_reason="none",
        confidence=1.0,
    )


def _hold_ungrounded_interaction_draft(
    draft: PatientReplyDraft,
    interaction_evidence: PatientInteractionEvidence,
) -> PatientReplyDraft:
    """Do not let food/alcohol/interaction answers leave without evidence."""
    if (
        not interaction_evidence.is_interaction_question
        or interaction_evidence.citations
        or draft.requires_pharmacist_review
    ):
        return draft
    return PatientReplyDraft(
        message=(
            "I need your pharmacist to review that interaction question before I answer. "
            "Please keep following your current instructions unless your pharmacist tells "
            "you otherwise."
        ),
        requires_pharmacist_review=True,
        escalation_reason="unclear_message",
        confidence=min(draft.confidence, 0.75),
    )


async def _load_treatment(session: AsyncSession, treatment_id: UUID) -> Treatment | None:
    result = await session.execute(
        select(Treatment)
        .where(Treatment.id == treatment_id)
        .options(selectinload(Treatment.medications))
    )
    return result.scalar_one_or_none()


async def _recent_message_context(
    session: AsyncSession,
    treatment_id: UUID,
    *,
    limit: int,
) -> list[ConversationMessageContext]:
    result = await session.execute(
        select(ConversationMessage)
        .where(ConversationMessage.treatment_id == treatment_id)
        .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [
        ConversationMessageContext(
            direction=message.direction,
            sender_type=message.sender_type,
            status=message.status,
            body=message.body,
        )
        for message in messages
    ]


async def _latest_analysis_summary(session: AsyncSession, treatment_id: UUID) -> str | None:
    result = await session.execute(
        select(TreatmentAnalysis)
        .where(
            TreatmentAnalysis.treatment_id == treatment_id,
            TreatmentAnalysis.status == "completed",
            TreatmentAnalysis.result.is_not(None),
        )
        .order_by(TreatmentAnalysis.created_at.desc())
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None or analysis.result is None:
        return None
    reasoning = analysis.result.get("reasoning")
    if not isinstance(reasoning, dict):
        return None
    summary = reasoning.get("summary")
    return summary if isinstance(summary, str) and summary.strip() else None

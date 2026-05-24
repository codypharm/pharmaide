"""Read-only audit feed queries for pharmacist/admin dashboards."""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AdherenceEvent,
    AuditLogEntry,
    ConversationMessage,
    KnowledgeDocument,
    Medication,
    PatientCheckIn,
    Treatment,
    TriageItem,
)


async def list_audit_log_entries(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    event_type: str | None = None,
    resource_type: str | None = None,
    actor_id: UUID | None = None,
    current_actor_id: UUID | None = None,
    scope_id: UUID | None = None,
) -> list[AuditLogEntry]:
    """Return recent audit entries without joining PHI-bearing tables."""
    statement = select(AuditLogEntry)
    scope_filter = _audit_scope_filter(scope_id=scope_id, current_actor_id=current_actor_id)
    if scope_filter is not None:
        statement = statement.where(scope_filter)
    if event_type is not None:
        statement = statement.where(AuditLogEntry.event_type == event_type)
    if resource_type is not None:
        statement = statement.where(AuditLogEntry.resource_type == resource_type)
    if actor_id is not None:
        statement = statement.where(AuditLogEntry.actor_id == actor_id)

    result = await session.scalars(
        statement.order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result)


def _audit_scope_filter(*, scope_id: UUID | None, current_actor_id: UUID | None):
    if scope_id is None and current_actor_id is None:
        return None

    allowed_conditions = []
    if current_actor_id is not None:
        allowed_conditions.append(AuditLogEntry.actor_id == current_actor_id)
    if scope_id is None:
        return or_(*allowed_conditions) if allowed_conditions else None

    scoped_treatment_ids = select(Treatment.id).where(Treatment.scope_id == scope_id)
    allowed_conditions.extend(
        [
            and_(
                AuditLogEntry.resource_type == "treatment",
                AuditLogEntry.resource_id.in_(scoped_treatment_ids),
            ),
            and_(
                AuditLogEntry.resource_type == "medication",
                AuditLogEntry.resource_id.in_(
                    select(Medication.id).where(Medication.treatment_id.in_(scoped_treatment_ids))
                ),
            ),
            and_(
                AuditLogEntry.resource_type == "conversation_message",
                AuditLogEntry.resource_id.in_(
                    select(ConversationMessage.id).where(
                        ConversationMessage.treatment_id.in_(scoped_treatment_ids)
                    )
                ),
            ),
            and_(
                AuditLogEntry.resource_type == "triage_item",
                AuditLogEntry.resource_id.in_(
                    select(TriageItem.id).where(TriageItem.treatment_id.in_(scoped_treatment_ids))
                ),
            ),
            and_(
                AuditLogEntry.resource_type == "adherence_event",
                AuditLogEntry.resource_id.in_(
                    select(AdherenceEvent.id).where(
                        AdherenceEvent.treatment_id.in_(scoped_treatment_ids)
                    )
                ),
            ),
            and_(
                AuditLogEntry.resource_type == "patient_check_in",
                AuditLogEntry.resource_id.in_(
                    select(PatientCheckIn.id).where(
                        PatientCheckIn.treatment_id.in_(scoped_treatment_ids)
                    )
                ),
            ),
            and_(
                AuditLogEntry.resource_type == "kb_document",
                AuditLogEntry.resource_id.in_(
                    select(KnowledgeDocument.id).where(KnowledgeDocument.uploaded_by == scope_id)
                ),
            ),
        ]
    )
    return or_(*allowed_conditions)

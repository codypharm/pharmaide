"""SQLAlchemy 2.0 declarative ORM models.

Schema is Postgres-shaped (UUID, JSONB, TIMESTAMPTZ) because the
production target is CockroachDB Serverless, which is wire-compatible.
Server-side defaults (gen_random_uuid, clock_timestamp) keep id/timestamp
logic out of Python so concurrent inserts can't race on it. clock_timestamp
(not now/transaction_timestamp) gives statement-level resolution so rows
written inside the same transaction get distinct created_at values — a
must-have for audit-trail / triage-feed ordering.

Forward-hook columns (langgraph_thread_id, rxnorm_id, audit_log.actor_id)
are nullable in this slice and get populated by later sprints.
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.db.base import Base

EMBEDDING_DIMENSIONS = 3072


class Vector(UserDefinedType[str]):
    """SQLAlchemy type for pgvector/Cockroach VECTOR columns."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"VECTOR({self.dimensions})"


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    dob: Mapped[date] = mapped_column(Date, nullable=False)
    # Institution-scoped uniqueness in real life; globally unique here
    # until multi-tenant lands.
    mrn: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Stored E.164 normalised by the wire-layer Pydantic validator.
    # NOT unique — duplicates currently allowed. WhatsApp routing in
    # Sprint 5 will decide the policy: UNIQUE(phone), UNIQUE(phone,
    # status='active'), or warn-but-allow with a lookup. Defer until
    # the routing consumer exists.
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    # Patient-specific allergy history used by later safety/CDS checks. Stored
    # as structured JSONB so we can add richer allergy metadata later.
    allergies: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    treatments: Mapped[list["Treatment"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )


class Treatment(Base):
    __tablename__ = "treatments"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    patient_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Lifecycle: pending → active (after Start Cycle) → completed | terminated.
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    # Chat ownership is separate from treatment automation. Pharmacist takeover
    # blocks free-text AI answers without stopping reminders or check-ins.
    chat_response_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ai_active'")
    )
    automation_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'")
    )
    clinical_objective: Mapped[str | None] = mapped_column(Text)
    treatment_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Populated by Sprint 3 when the LangGraph thread is materialised.
    langgraph_thread_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    patient: Mapped[Patient] = relationship(back_populates="treatments")
    medications: Mapped[list["Medication"]] = relationship(
        back_populates="treatment", cascade="all, delete-orphan", order_by="Medication.ordinal"
    )
    analyses: Mapped[list["TreatmentAnalysis"]] = relationship(
        back_populates="treatment", cascade="all, delete-orphan"
    )
    check_ins: Mapped[list["PatientCheckIn"]] = relationship(
        back_populates="treatment", cascade="all, delete-orphan"
    )
    adherence_events: Mapped[list["AdherenceEvent"]] = relationship(
        back_populates="treatment", cascade="all, delete-orphan"
    )
    conversation_messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="treatment", cascade="all, delete-orphan"
    )
    triage_items: Mapped[list["TriageItem"]] = relationship(
        back_populates="treatment", cascade="all, delete-orphan"
    )


class Medication(Base):
    __tablename__ = "medications"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    treatment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("treatments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    dosage: Mapped[str] = mapped_column(Text, nullable=False)
    # Freetext until Sprint 3 introduces the schedule generator's parser.
    frequency: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    # Preserves the pharmacist's input order so the regimen displays the
    # way it was entered, regardless of insert ordering.
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # Populated by Sprint 3 via RxNorm API after pharmacist approval.
    rxnorm_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    treatment: Mapped[Treatment] = relationship(back_populates="medications")
    adherence_events: Mapped[list["AdherenceEvent"]] = relationship(
        back_populates="medication", cascade="all, delete-orphan"
    )


class TreatmentAnalysis(Base):
    __tablename__ = "treatment_analyses"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    treatment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("treatments.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error_text: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    treatment: Mapped[Treatment] = relationship(back_populates="analyses")

    __table_args__ = (
        Index("idx_treatment_analyses_treatment_created", "treatment_id", created_at.desc()),
        Index(
            "uq_treatment_analyses_active_treatment",
            "treatment_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )


class PatientCheckIn(Base):
    __tablename__ = "patient_check_ins"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    treatment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("treatments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    treatment: Mapped[Treatment] = relationship(back_populates="check_ins")

    __table_args__ = (
        Index("idx_patient_check_ins_treatment_created", "treatment_id", created_at.desc()),
    )


class AdherenceEvent(Base):
    __tablename__ = "adherence_events"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    treatment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("treatments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    medication_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("medications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # May contain patient-provided context. Keep it out of audit/log payloads.
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    treatment: Mapped[Treatment] = relationship(back_populates="adherence_events")
    medication: Mapped[Medication] = relationship(back_populates="adherence_events")

    __table_args__ = (
        Index("idx_adherence_events_treatment_created", "treatment_id", created_at.desc()),
        Index("idx_adherence_events_medication_scheduled", "medication_id", "scheduled_for"),
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    treatment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("treatments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    sender_type: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # Patient conversations are clinical data. Store it once here, but keep
    # message text out of logs and audit payloads.
    body: Mapped[str] = mapped_column(Text, nullable=False)
    safety_hold_reason: Mapped[str | None] = mapped_column(Text)
    external_message_id: Mapped[str | None] = mapped_column(Text)
    # Inbound WhatsApp messages can arrive in bursts. processed_at marks rows
    # already included in an aggregated patient turn.
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    treatment: Mapped[Treatment] = relationship(back_populates="conversation_messages")

    __table_args__ = (
        Index("idx_conversation_messages_treatment_created", "treatment_id", created_at.desc()),
        Index(
            "idx_conversation_messages_unprocessed",
            "treatment_id",
            "processed_at",
            postgresql_where=text("direction = 'inbound' AND sender_type = 'patient'"),
        ),
    )


class TriageItem(Base):
    __tablename__ = "triage_items"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    treatment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("treatments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_message_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("conversation_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    treatment: Mapped[Treatment] = relationship(back_populates="triage_items")
    conversation_message: Mapped[ConversationMessage | None] = relationship()

    __table_args__ = (
        Index("idx_triage_items_status_created", "status", created_at.desc()),
        Index("idx_triage_items_treatment_created", "treatment_id", created_at.desc()),
    )


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Nullable until auth lands. Pre-auth writes log NULL ("system actor").
    actor_id: Mapped[UUID | None] = mapped_column(Uuid)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # JSONB rather than JSON for indexable queries on the payload later.
    # Per HIPAA "minimum necessary," PHI stays out of this column.
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    __table_args__ = (Index("idx_audit_log_resource", "resource_type", "resource_id"),)


class KnowledgeDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[UUID | None] = mapped_column(Uuid)
    # Ingestion failures need a pharmacist-safe operational message without
    # forcing a second migration when the async ingestion worker lands.
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="KnowledgeChunk.ordinal"
    )

    __table_args__ = (
        Index(
            "uq_kb_documents_source_owner_uri",
            "source_type",
            "source_uri",
            "uploaded_by",
            unique=True,
        ),
    )


class KnowledgeChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("kb_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[str] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("idx_kb_chunks_document_ordinal", "document_id", "ordinal"),
    )

"""SQLAlchemy 2.0 declarative ORM models.

Schema is Postgres-shaped (UUID, JSONB, TIMESTAMPTZ) because the
production target is CockroachDB Serverless, which is wire-compatible.
Server-side defaults (gen_random_uuid, now()) keep id/timestamp logic
out of Python so concurrent inserts can't race on it.

Forward-hook columns (langgraph_thread_id, rxnorm_id, audit_log.actor_id)
are nullable in this slice and get populated by later sprints.
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


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
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
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
    clinical_objective: Mapped[str | None] = mapped_column(Text)
    # Populated by Sprint 3 when the LangGraph thread is materialised.
    langgraph_thread_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    patient: Mapped[Patient] = relationship(back_populates="treatments")
    medications: Mapped[list["Medication"]] = relationship(
        back_populates="treatment", cascade="all, delete-orphan", order_by="Medication.ordinal"
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
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    treatment: Mapped[Treatment] = relationship(back_populates="medications")


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
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("idx_audit_log_resource", "resource_type", "resource_id"),)

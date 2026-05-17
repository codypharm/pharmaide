"""Deterministic course completion report foundation.

This module builds structured end-of-course facts only. It intentionally avoids
copying patient messages, adherence notes, or medication names into the report
so the first reporting layer stays low-risk and PHI-minimised.
"""

from collections import Counter
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AdherenceEvent, AuditLogEntry, PatientCheckIn, Treatment, TriageItem


class TreatmentNotFound(Exception):
    """Raised when a course-completion report references a missing treatment."""


class CourseCompletionReportCounts(BaseModel):
    """Count group used by deterministic course-completion summaries."""

    model_config = ConfigDict(extra="forbid")

    total_count: int = Field(ge=0)
    by_status: dict[str, int] = Field(default_factory=dict)


class PatientUpdateReportCounts(BaseModel):
    """Patient update counts without patient message text."""

    model_config = ConfigDict(extra="forbid")

    total_count: int = Field(ge=0)
    by_report_type: dict[str, int] = Field(default_factory=dict)


class TriageReportCounts(BaseModel):
    """Triage counts without draft or patient-message body text."""

    model_config = ConfigDict(extra="forbid")

    total_count: int = Field(ge=0)
    by_status: dict[str, int] = Field(default_factory=dict)
    by_reason: dict[str, int] = Field(default_factory=dict)


class CourseCompletionReport(BaseModel):
    """Validated deterministic report data for a completed treatment course."""

    model_config = ConfigDict(extra="forbid")

    treatment_id: UUID
    patient_id: UUID
    status: str
    treatment_start_at: datetime | None
    created_at: datetime
    medication_count: int = Field(ge=0)
    adherence: CourseCompletionReportCounts
    patient_updates: PatientUpdateReportCounts
    triage: TriageReportCounts


async def build_course_completion_report(
    session: AsyncSession,
    *,
    treatment_id: UUID,
) -> CourseCompletionReport:
    """Build a structured, PHI-minimised course report from persisted rows."""
    treatment = await _load_treatment(session, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    adherence_events = await _load_adherence_events(session, treatment_id)
    check_ins = await _load_patient_check_ins(session, treatment_id)
    triage_items = await _load_triage_items(session, treatment_id)

    return CourseCompletionReport(
        treatment_id=treatment.id,
        patient_id=treatment.patient_id,
        status=treatment.status,
        treatment_start_at=treatment.treatment_start_at,
        created_at=treatment.created_at,
        medication_count=len(treatment.medications),
        adherence=CourseCompletionReportCounts(
            total_count=len(adherence_events),
            by_status=_count_by(adherence_events, "status"),
        ),
        patient_updates=PatientUpdateReportCounts(
            total_count=len(check_ins),
            by_report_type=_count_by(check_ins, "report_type"),
        ),
        triage=TriageReportCounts(
            total_count=len(triage_items),
            by_status=_count_by(triage_items, "status"),
            by_reason=_count_by(triage_items, "reason"),
        ),
    )


def audit_course_completion_report_viewed(
    session: AsyncSession,
    report: CourseCompletionReport,
) -> None:
    """Record report access with aggregate counts only, never patient text."""
    session.add(
        AuditLogEntry(
            event_type="completion_report_viewed",
            resource_type="treatment",
            resource_id=report.treatment_id,
            payload={
                "report_status": report.status,
                "medication_count": report.medication_count,
                "adherence_total_count": report.adherence.total_count,
                "patient_update_total_count": report.patient_updates.total_count,
                "triage_total_count": report.triage.total_count,
            },
        )
    )


async def _load_treatment(session: AsyncSession, treatment_id: UUID) -> Treatment | None:
    result = await session.execute(
        select(Treatment)
        .where(Treatment.id == treatment_id)
        .options(selectinload(Treatment.medications))
    )
    return result.scalar_one_or_none()


async def _load_adherence_events(
    session: AsyncSession,
    treatment_id: UUID,
) -> list[AdherenceEvent]:
    result = await session.execute(
        select(AdherenceEvent).where(AdherenceEvent.treatment_id == treatment_id)
    )
    return list(result.scalars())


async def _load_patient_check_ins(
    session: AsyncSession,
    treatment_id: UUID,
) -> list[PatientCheckIn]:
    result = await session.execute(
        select(PatientCheckIn).where(PatientCheckIn.treatment_id == treatment_id)
    )
    return list(result.scalars())


async def _load_triage_items(session: AsyncSession, treatment_id: UUID) -> list[TriageItem]:
    result = await session.execute(
        select(TriageItem).where(TriageItem.treatment_id == treatment_id)
    )
    return list(result.scalars())


def _count_by(rows: list[object], attribute: str) -> dict[str, int]:
    counts = Counter(str(getattr(row, attribute)) for row in rows)
    return dict(sorted(counts.items()))

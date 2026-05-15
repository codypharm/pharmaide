"""Validated envelopes for Sprint 3 treatment analysis.

These models are the boundary between agent/LLM output and medication logic.
Anything produced by an LLM must validate here before the rest of the app uses
it, which keeps raw JSON out of the orchestration layer.
"""

from datetime import datetime, timedelta
from typing import Literal, NotRequired, TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DDISeverity = Literal["minor", "moderate", "major"]
KnowledgeSourceType = Literal["user_upload", "dailymed"]
ClinicalSafetySourceType = Literal["model_review"]
PatientCheckInReportType = Literal[
    "not_improving",
    "side_effect",
    "feeling_better",
    "general_update",
    "missed_dose",
]
PatientCheckInSource = Literal["patient", "pharmacist", "system"]


class AnalysisEnvelope(BaseModel):
    """Base class for strict analysis payloads."""

    model_config = ConfigDict(extra="forbid")


class MedicationGrounding(AnalysisEnvelope):
    """RxNorm grounding for one medication entered by the pharmacist."""

    medication_id: UUID
    medication_name: str = Field(min_length=1)
    rxcui: str | None = None
    normalized_name: str | None = None
    confidence: float = Field(ge=0, le=1)


class DDIWarning(AnalysisEnvelope):
    """Drug interaction warning between grounded medications."""

    medication_ids: list[UUID] = Field(min_length=2)
    severity: DDISeverity
    description: str = Field(min_length=1)
    source: str = Field(min_length=1)


class ReminderSlot(AnalysisEnvelope):
    """One deterministic reminder offset from the treatment start."""

    medication_id: UUID
    offset_from_start: timedelta
    human_label: str = Field(min_length=1)


class Schedule(AnalysisEnvelope):
    """Preview schedule generated for pharmacist review."""

    reminders: list[ReminderSlot]


class ClinicalReasoning(AnalysisEnvelope):
    """LLM-generated clinical reasoning, validated before persistence."""

    summary: str = Field(min_length=1)
    red_flags: list[str]
    confidence: float = Field(ge=0, le=1)


class ClinicalReasoningWithSchedule(AnalysisEnvelope):
    """LLM output when ambiguous schedules require a validated proposal."""

    reasoning: ClinicalReasoning
    schedule: Schedule | None


class ClinicalSafetyReview(AnalysisEnvelope):
    """LLM fallback review when licensed clinical data is unavailable.

    This is not a database-confirmed interaction result. It is pharmacist-review
    support until a licensed Lexicomp/DrugBank-style provider is available.
    """

    source_type: ClinicalSafetySourceType = "model_review"
    possible_interactions: list[str] = Field(default_factory=list)
    monitoring_concerns: list[str] = Field(default_factory=list)
    counseling_points: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    requires_pharmacist_review: Literal[True] = True


class KBCitation(AnalysisEnvelope):
    """Knowledge-base passage retrieved for clinical reasoning citation."""

    chunk_id: UUID
    document_id: UUID
    source_type: KnowledgeSourceType = "user_upload"
    document_title: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    text: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)


class PatientCheckInState(AnalysisEnvelope):
    """Patient-reported treatment status supplied as analysis context."""

    id: UUID
    report_type: PatientCheckInReportType
    source: PatientCheckInSource
    message: str = Field(min_length=1)
    observed_at: datetime | None = None
    created_at: datetime


class AnalysisResult(AnalysisEnvelope):
    """Durable analysis payload stored on treatment_analyses.result."""

    groundings: list[MedicationGrounding]
    ddi_warnings: list[DDIWarning]
    schedule: Schedule | None
    kb_citations: list[KBCitation] = Field(default_factory=list)
    clinical_safety_review: ClinicalSafetyReview | None = None
    reasoning: ClinicalReasoning | None
    degraded: bool
    partial_results: bool = False
    completed_stages: list[str] = Field(default_factory=list)


class MedicationState(TypedDict):
    """Medication shape passed through analysis graph state."""

    id: UUID
    name: str
    dosage: str
    frequency: str
    duration: str
    objective: str | None


class AnalysisState(TypedDict, total=False):
    """Mutable LangGraph state shared by analysis nodes."""

    treatment_id: UUID
    medications: list[MedicationState]
    patient_check_ins: NotRequired[list[PatientCheckInState]]
    groundings: list[MedicationGrounding]
    ddi_warnings: list[DDIWarning]
    schedule: Schedule | None
    kb_citations: NotRequired[list[KBCitation]]
    clinical_safety_review: NotRequired[ClinicalSafetyReview | None]
    reasoning: ClinicalReasoning | None
    degraded: bool
    needs_llm_parse: NotRequired[bool]
    completed_stages: NotRequired[list[str]]

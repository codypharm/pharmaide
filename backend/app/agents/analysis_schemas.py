"""Validated envelopes for Sprint 3 treatment analysis.

These models are the boundary between agent/LLM output and medication logic.
Anything produced by an LLM must validate here before the rest of the app uses
it, which keeps raw JSON out of the orchestration layer.
"""

from datetime import timedelta
from typing import Literal, NotRequired, TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DDISeverity = Literal["minor", "moderate", "major"]


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


class KBCitation(AnalysisEnvelope):
    """Knowledge-base passage retrieved for clinical reasoning citation."""

    chunk_id: UUID
    document_id: UUID
    document_title: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    text: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)


class AnalysisResult(AnalysisEnvelope):
    """Durable analysis payload stored on treatment_analyses.result."""

    groundings: list[MedicationGrounding]
    ddi_warnings: list[DDIWarning]
    schedule: Schedule | None
    kb_citations: list[KBCitation] = Field(default_factory=list)
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
    groundings: list[MedicationGrounding]
    ddi_warnings: list[DDIWarning]
    schedule: Schedule | None
    kb_citations: NotRequired[list[KBCitation]]
    reasoning: ClinicalReasoning | None
    degraded: bool
    needs_llm_parse: NotRequired[bool]
    completed_stages: NotRequired[list[str]]

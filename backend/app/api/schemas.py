"""Pydantic wire models for the ingestion API.

Separate from app.db.models on purpose: these describe the *contract*
between frontend and backend. Storage shapes evolve independently —
e.g. when audit_log gains an actor_id column, the wire shape doesn't
need to change.
"""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber

from app.agents.safety_schemas import PatientDraftSafetyDecision

IngestionMethod = Literal["structured", "manual", "vision"]
PatientCheckInReportType = Literal[
    "not_improving",
    "side_effect",
    "feeling_better",
    "general_update",
    "missed_dose",
]
PatientCheckInSource = Literal["patient", "pharmacist", "system"]
AdherenceEventStatus = Literal["taken", "missed", "held", "skipped"]
AdherenceEventSource = Literal["patient", "pharmacist", "system"]
ConversationMessageDirection = Literal["inbound", "outbound"]
ConversationMessageSender = Literal["patient", "assistant", "pharmacist", "system"]
ConversationMessageChannel = Literal["whatsapp", "dashboard", "system"]
ConversationMessageStatus = Literal[
    "received",
    "draft_ready",
    "held_for_review",
    "approved",
    "rejected",
    "queued",
    "sent",
    "failed",
]
ChatResponseMode = Literal["ai_active", "pharmacist_takeover"]
AutomationMode = Literal["active", "paused"]
TriageReason = Literal[
    "input_guard",
    "referee",
    "output_guard",
    "adverse_event",
    "emergency",
    "side_effect",
    "dose_change_request",
    "diagnosis_request",
    "unclear_message",
    "non_responsive",
]
TriageStatus = Literal["open", "acknowledged", "resolved"]
AllergyName = Annotated[str, Field(min_length=1, max_length=200)]


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dob: date
    mrn: str = Field(min_length=1, max_length=64)
    # PhoneNumber normalises to RFC3966 ("tel:+15551234567"); rejects
    # non-E.164 input. Required because WhatsApp Business API needs it.
    phone: PhoneNumber
    allergies: list[AllergyName] = Field(default_factory=list, max_length=50)

    @field_validator("allergies")
    @classmethod
    def normalise_allergies(cls, allergies: list[str]) -> list[str]:
        """Strip display whitespace and reject blank allergy entries."""
        normalised = [allergy.strip() for allergy in allergies]
        if any(not allergy for allergy in normalised):
            raise ValueError("allergy entries must not be blank")
        return normalised


class MedicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dosage: str = Field(min_length=1, max_length=50)
    # Freetext until Sprint 3's schedule generator parses it.
    frequency: str = Field(min_length=1, max_length=50)
    duration: str = Field(min_length=1, max_length=50)
    objective: str | None = Field(default=None, max_length=500)


class TreatmentCreate(BaseModel):
    clinical_objective: str | None = Field(default=None, max_length=1000)
    treatment_start_at: datetime | None = None

    @field_validator("treatment_start_at")
    @classmethod
    def require_timezone_for_start(cls, value: datetime | None) -> datetime | None:
        """Reject ambiguous local times before schedule math depends on them."""
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("treatment_start_at must include a timezone")
        return value


class CreateTreatmentRequest(BaseModel):
    patient: PatientCreate
    treatment: TreatmentCreate
    medications: list[MedicationCreate] = Field(min_length=1)
    ingestion_method: IngestionMethod


class CreateTreatmentResponse(BaseModel):
    treatment_id: UUID
    patient_id: UUID
    analysis_id: UUID | None = None


class AnalyzeTreatmentResponse(BaseModel):
    analysis_id: UUID


class PatientCheckInCreate(BaseModel):
    report_type: PatientCheckInReportType
    source: PatientCheckInSource = "patient"
    message: str = Field(min_length=1, max_length=2000)
    observed_at: datetime | None = None

    @field_validator("message")
    @classmethod
    def normalise_message(cls, value: str) -> str:
        """Store patient reports without surrounding transport whitespace."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be blank")
        return stripped

    @field_validator("observed_at")
    @classmethod
    def require_timezone_for_observed_at(cls, value: datetime | None) -> datetime | None:
        """Patient timelines need an absolute instant, not browser-local ambiguity."""
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("observed_at must include a timezone")
        return value


class PatientCheckInView(BaseModel):
    id: UUID
    treatment_id: UUID
    report_type: str
    source: str
    message: str
    observed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PatientCheckInList(BaseModel):
    items: list[PatientCheckInView]


class AdherenceEventCreate(BaseModel):
    medication_id: UUID
    status: AdherenceEventStatus
    source: AdherenceEventSource = "patient"
    scheduled_for: datetime | None = None
    occurred_at: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("scheduled_for", "occurred_at")
    @classmethod
    def require_timezone_for_event_time(cls, value: datetime | None) -> datetime | None:
        """Reminder state needs absolute instants, not browser-local ambiguity."""
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("event times must include a timezone")
        return value

    @field_validator("note")
    @classmethod
    def normalise_note(cls, value: str | None) -> str | None:
        """Keep optional notes useful without storing whitespace-only strings."""
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return stripped


class AdherenceEventView(BaseModel):
    id: UUID
    treatment_id: UUID
    medication_id: UUID
    status: str
    source: str
    scheduled_for: datetime | None
    occurred_at: datetime | None
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdherenceEventList(BaseModel):
    items: list[AdherenceEventView]


class ConversationMessageView(BaseModel):
    id: UUID
    treatment_id: UUID
    direction: ConversationMessageDirection
    sender_type: ConversationMessageSender
    channel: ConversationMessageChannel
    status: ConversationMessageStatus
    body: str
    safety_hold_reason: str | None
    external_message_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationMessageList(BaseModel):
    items: list[ConversationMessageView]


class ConversationTurnView(BaseModel):
    inbound_message: ConversationMessageView
    assistant_message: ConversationMessageView
    safety_decision: PatientDraftSafetyDecision


class ConversationTurnCreate(BaseModel):
    patient_message: str = Field(min_length=1, max_length=4000)
    assistant_draft: str = Field(min_length=1, max_length=4000)
    prescription_context: str = Field(min_length=1, max_length=8000)

    @field_validator("patient_message", "assistant_draft", "prescription_context")
    @classmethod
    def normalise_text(cls, value: str) -> str:
        """Reject transport whitespace before safety review sees the turn."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("conversation text must not be blank")
        return stripped


class PatientConversationMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def normalise_message(cls, value: str) -> str:
        """Store inbound patient messages without transport whitespace."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be blank")
        return stripped


class PharmacistConversationMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def normalise_message(cls, value: str) -> str:
        """Store outbound pharmacist messages without transport whitespace."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be blank")
        return stripped


class PatientReplyDraftCreate(BaseModel):
    patient_message: str = Field(min_length=1, max_length=4000)

    @field_validator("patient_message")
    @classmethod
    def normalise_patient_message(cls, value: str) -> str:
        """Reject blank patient messages before draft generation."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("patient_message must not be blank")
        return stripped


class TriageItemView(BaseModel):
    id: UUID
    treatment_id: UUID
    conversation_message_id: UUID | None
    reason: TriageReason
    status: TriageStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class TriageItemList(BaseModel):
    items: list[TriageItemView]


class TriageApprovalView(BaseModel):
    triage_item: TriageItemView
    approved_message: ConversationMessageView


class TriageDeliveryView(BaseModel):
    triage_item: TriageItemView
    queued_message: ConversationMessageView


class TriageRejectionView(BaseModel):
    triage_item: TriageItemView
    rejected_message: ConversationMessageView


class TriageItemUpdate(BaseModel):
    status: TriageStatus


class TreatmentAnalysisSnapshot(BaseModel):
    id: UUID
    treatment_id: UUID
    status: str
    result: dict[str, object] | None
    error_text: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TreatmentAnalysisView(TreatmentAnalysisSnapshot):
    last_completed: TreatmentAnalysisSnapshot | None = None


class PatientView(BaseModel):
    id: UUID
    name: str
    dob: date
    mrn: str
    phone: str
    allergies: list[str]

    model_config = {"from_attributes": True}


class TreatmentView(BaseModel):
    id: UUID
    patient_id: UUID
    status: str
    chat_response_mode: ChatResponseMode
    automation_mode: AutomationMode
    clinical_objective: str | None
    treatment_start_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TreatmentChatResponseModeUpdate(BaseModel):
    chat_response_mode: ChatResponseMode


class MedicationView(BaseModel):
    id: UUID
    name: str
    dosage: str
    frequency: str
    duration: str
    objective: str | None
    ordinal: int

    model_config = {"from_attributes": True}


class TreatmentDetail(BaseModel):
    patient: PatientView
    treatment: TreatmentView
    medications: list[MedicationView]


class TreatmentListItem(BaseModel):
    """Lean row for the GET /treatments list view.

    Trades the full medications array for count + first-name preview so
    a feed/queue UI can render without per-row roundtrips.
    """

    patient: PatientView
    treatment: TreatmentView
    medication_count: int
    first_medication_name: str | None


class TreatmentList(BaseModel):
    items: list[TreatmentListItem]

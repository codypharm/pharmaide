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

IngestionMethod = Literal["structured", "manual", "vision"]
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


class TreatmentAnalysisView(BaseModel):
    id: UUID
    treatment_id: UUID
    status: str
    result: dict[str, object] | None
    error_text: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


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
    clinical_objective: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


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

"""Pydantic wire models for the ingestion API.

Separate from app.db.models on purpose: these describe the *contract*
between frontend and backend. Storage shapes evolve independently —
e.g. when audit_log gains an actor_id column, the wire shape doesn't
need to change.
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic_extra_types.phone_numbers import PhoneNumber

IngestionMethod = Literal["structured", "manual", "vision"]


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dob: date
    mrn: str = Field(min_length=1, max_length=64)
    # PhoneNumber normalises to RFC3966 ("tel:+15551234567"); rejects
    # non-E.164 input. Required because WhatsApp Business API needs it.
    phone: PhoneNumber


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


class PatientView(BaseModel):
    id: UUID
    name: str
    dob: date
    mrn: str
    phone: str

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

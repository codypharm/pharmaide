"""Validated envelopes for prescription image extraction.

Vision extraction is intentionally a draft contract: fields may be missing
because the model must not infer unreadable patient or medication data.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractionEnvelope(BaseModel):
    """Base class for strict extraction payloads returned by the vision agent."""

    model_config = ConfigDict(extra="forbid")


class ExtractedPatientConfidence(ExtractionEnvelope):
    """Per-field confidence for values that map to PatientCreate."""

    name: float | None = Field(default=None, ge=0, le=1)
    dob: float | None = Field(default=None, ge=0, le=1)
    mrn: float | None = Field(default=None, ge=0, le=1)
    phone: float | None = Field(default=None, ge=0, le=1)


class ExtractedTreatmentConfidence(ExtractionEnvelope):
    """Per-field confidence for values that map to TreatmentCreate."""

    clinical_objective: float | None = Field(default=None, ge=0, le=1)


class ExtractedMedicationConfidence(ExtractionEnvelope):
    """Per-field confidence for values that map to MedicationCreate."""

    name: float | None = Field(default=None, ge=0, le=1)
    dosage: float | None = Field(default=None, ge=0, le=1)
    frequency: float | None = Field(default=None, ge=0, le=1)
    duration: float | None = Field(default=None, ge=0, le=1)
    objective: float | None = Field(default=None, ge=0, le=1)


class ExtractedPatient(ExtractionEnvelope):
    """Nullable patient draft that preserves PatientCreate field names."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    dob: date | None = None
    mrn: str | None = Field(default=None, min_length=1, max_length=64)
    # Keep this as text: extraction should display what is visible, while the
    # final create request remains responsible for WhatsApp-ready validation.
    phone: str | None = Field(default=None, min_length=1, max_length=64)
    confidence: ExtractedPatientConfidence = Field(
        default_factory=ExtractedPatientConfidence
    )


class ExtractedTreatment(ExtractionEnvelope):
    """Nullable treatment draft that preserves TreatmentCreate field names."""

    clinical_objective: str | None = Field(default=None, max_length=1000)
    confidence: ExtractedTreatmentConfidence = Field(
        default_factory=ExtractedTreatmentConfidence
    )


class ExtractedMedication(ExtractionEnvelope):
    """Nullable medication draft that preserves MedicationCreate field names."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    dosage: str | None = Field(default=None, min_length=1, max_length=50)
    frequency: str | None = Field(default=None, min_length=1, max_length=50)
    duration: str | None = Field(default=None, min_length=1, max_length=50)
    objective: str | None = Field(default=None, max_length=500)
    confidence: ExtractedMedicationConfidence = Field(
        default_factory=ExtractedMedicationConfidence
    )


class ExtractedPrescription(ExtractionEnvelope):
    """Full vision extraction result before pharmacist review and submit."""

    patient: ExtractedPatient = Field(default_factory=ExtractedPatient)
    treatment: ExtractedTreatment = Field(default_factory=ExtractedTreatment)
    medications: list[ExtractedMedication] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def to_treatment_create_draft(self) -> dict[str, Any]:
        """Return the existing CreateTreatmentRequest shape for UI prefilling."""

        return {
            "patient": self.patient.model_dump(
                mode="json",
                exclude={"confidence"},
            ),
            "treatment": self.treatment.model_dump(
                mode="json",
                exclude={"confidence"},
            ),
            "medications": [
                medication.model_dump(mode="json", exclude={"confidence"})
                for medication in self.medications
            ],
            "ingestion_method": "vision",
        }


ExtractionMethod = Literal["vision"]

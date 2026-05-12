"""Pydantic envelopes for prescription image extraction."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.agents.extraction_schemas import (
    ExtractedMedication,
    ExtractedMedicationConfidence,
    ExtractedPatient,
    ExtractedPatientConfidence,
    ExtractedPrescription,
    ExtractedTreatment,
    ExtractedTreatmentConfidence,
)


def test_extracted_prescription_keeps_treatment_create_shape_nullable() -> None:
    prescription = ExtractedPrescription(
        patient=ExtractedPatient(
            name="Ada Lovelace",
            dob=date(1815, 12, 10),
            mrn=None,
            phone=None,
            confidence=ExtractedPatientConfidence(
                name=0.94,
                dob=0.72,
                mrn=None,
                phone=None,
            ),
        ),
        treatment=ExtractedTreatment(
            clinical_objective="Reduce blood pressure.",
            confidence=ExtractedTreatmentConfidence(clinical_objective=0.81),
        ),
        medications=[
            ExtractedMedication(
                name="Lisinopril",
                dosage="10 mg",
                frequency="once daily",
                duration=None,
                objective=None,
                confidence=ExtractedMedicationConfidence(
                    name=0.97,
                    dosage=0.9,
                    frequency=0.88,
                    duration=None,
                    objective=None,
                ),
            )
        ],
        warnings=["duration not visible"],
    )

    draft = prescription.to_treatment_create_draft()

    assert draft == {
        "patient": {
            "name": "Ada Lovelace",
            "dob": "1815-12-10",
            "mrn": None,
            "phone": None,
        },
        "treatment": {"clinical_objective": "Reduce blood pressure."},
        "medications": [
            {
                "name": "Lisinopril",
                "dosage": "10 mg",
                "frequency": "once daily",
                "duration": None,
                "objective": None,
            }
        ],
        "ingestion_method": "vision",
    }


def test_extraction_schema_allows_missing_values_without_inventing_data() -> None:
    prescription = ExtractedPrescription(
        patient=ExtractedPatient(),
        treatment=ExtractedTreatment(),
        medications=[ExtractedMedication()],
    )

    assert prescription.patient.name is None
    assert prescription.treatment.clinical_objective is None
    assert prescription.medications[0].dosage is None
    assert prescription.warnings == []


def test_extraction_confidence_rejects_out_of_range_values() -> None:
    with pytest.raises(ValidationError):
        ExtractedMedicationConfidence(name=1.2)


def test_extraction_envelopes_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ExtractedPatient.model_validate(
            {
                "name": "Ada Lovelace",
                "dob": None,
                "mrn": None,
                "phone": None,
                "confidence": {},
                "raw_ocr_text": "do not persist raw extraction text",
            }
        )

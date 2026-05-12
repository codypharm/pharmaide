"""PydanticAI prescription image extraction agent."""

import structlog
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import Model

from app.agents.extraction_schemas import ExtractedPrescription

log = structlog.get_logger(__name__)

EXTRACTION_INSTRUCTIONS = """
You are PharmaAide's prescription image extraction agent.
Extract only visible prescription content into the validated schema.
Do not infer, correct, normalize, or complete missing patient or medication data.
Return null for fields you cannot read confidently.
Use warnings for unreadable, ambiguous, cropped, or mostly handwritten content.
Never include raw OCR text or extra fields.
This output is a pharmacist-review draft, not a clinical decision.
"""

EXTRACTION_PROMPT = "Extract the prescription image into the validated schema."


def build_extraction_agent(
    model: Model | str = "openai:gpt-5.4-mini",
) -> Agent[None, ExtractedPrescription]:
    """Build the typed PydanticAI agent used for vision extraction."""
    return Agent(
        model,
        output_type=ExtractedPrescription,
        instructions=EXTRACTION_INSTRUCTIONS,
        defer_model_check=True,
    )


async def extract_prescription_image(
    image: bytes,
    media_type: str,
    *,
    agent: Agent[None, ExtractedPrescription] | None = None,
) -> ExtractedPrescription:
    """Extract a prescription image into a validated pharmacist-review draft."""
    extraction_agent = agent or build_extraction_agent()
    result = await extraction_agent.run(
        [
            EXTRACTION_PROMPT,
            BinaryContent(data=image, media_type=media_type),
        ]
    )
    prescription = result.output
    _log_extraction_summary(prescription, media_type=media_type, size_bytes=len(image))
    return prescription


def _log_extraction_summary(
    prescription: ExtractedPrescription,
    *,
    media_type: str,
    size_bytes: int,
) -> None:
    log.info(
        "prescription_extracted",
        media_type=media_type,
        size_bytes=size_bytes,
        medication_count=len(prescription.medications),
        warning_count=len(prescription.warnings),
        patient_field_completeness={
            "name": prescription.patient.name is not None,
            "dob": prescription.patient.dob is not None,
            "mrn": prescription.patient.mrn is not None,
            "phone": prescription.patient.phone is not None,
        },
        treatment_field_completeness={
            "clinical_objective": prescription.treatment.clinical_objective is not None,
        },
        medication_field_completeness=[
            {
                "name": medication.name is not None,
                "dosage": medication.dosage is not None,
                "frequency": medication.frequency is not None,
                "duration": medication.duration is not None,
                "objective": medication.objective is not None,
            }
            for medication in prescription.medications
        ],
    )

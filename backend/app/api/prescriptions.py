"""Prescription extraction route handlers."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import SecretStr
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.extraction import build_extraction_agent, extract_prescription_image
from app.agents.extraction_schemas import ExtractedPrescription
from app.config import Settings, get_settings
from app.db.engine import get_session
from app.db.models import AuditLogEntry
from app.services.image_guard import GuardedImage, ImageGuardError, validate_prescription_image

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_extraction_agent(settings: SettingsDep) -> Agent[None, ExtractedPrescription]:
    """FastAPI dependency seam for tests and later provider configuration."""
    return build_configured_extraction_agent(settings.openai_api_key)


def build_configured_extraction_agent(
    openai_api_key: SecretStr | None,
) -> Agent[None, ExtractedPrescription]:
    """Bridge PHARMAIDE_OPENAI_API_KEY into PydanticAI's OpenAI provider."""
    if openai_api_key is None:
        return build_extraction_agent()
    return build_extraction_agent(
        OpenAIResponsesModel(
            "gpt-5.4-mini",
            provider=OpenAIProvider(api_key=openai_api_key.get_secret_value()),
        )
    )


ExtractionAgentDep = Annotated[Agent[None, ExtractedPrescription], Depends(get_extraction_agent)]

router = APIRouter(prefix="/prescriptions")


@router.post(
    "/extract",
    response_model=ExtractedPrescription,
)
async def extract_prescription(
    session: SessionDep,
    agent: ExtractionAgentDep,
    file: Annotated[UploadFile, File()],
) -> ExtractedPrescription | JSONResponse:
    extraction_id = uuid4()
    data = await file.read()
    _audit_started(
        session,
        extraction_id=extraction_id,
        size_bytes=len(data),
        declared_mime=file.content_type,
    )

    try:
        image = validate_prescription_image(data, declared_mime=file.content_type)
        prescription = await extract_prescription_image(
            image.data,
            image.media_type,
            agent=agent,
        )
    except ImageGuardError as exc:
        _audit_failed(
            session,
            extraction_id=extraction_id,
            error=exc.code,
            size_bytes=len(data),
            declared_mime=file.content_type,
        )
        return JSONResponse(status_code=422, content={"detail": {"error": exc.code}})
    except Exception as exc:
        error_code = _extraction_failure_code(exc)
        _audit_failed(
            session,
            extraction_id=extraction_id,
            error=error_code,
            size_bytes=len(data),
            declared_mime=file.content_type,
        )
        return JSONResponse(status_code=422, content={"detail": {"error": error_code}})

    _audit_completed(session, extraction_id=extraction_id, image=image, prescription=prescription)
    return prescription


def _audit_started(
    session: AsyncSession,
    *,
    extraction_id: UUID,
    size_bytes: int,
    declared_mime: str | None,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="extraction_started",
            resource_type="extraction",
            resource_id=extraction_id,
            payload={
                "size_bytes": size_bytes,
                "declared_mime": declared_mime,
            },
        )
    )


def _audit_completed(
    session: AsyncSession,
    *,
    extraction_id: UUID,
    image: GuardedImage,
    prescription: ExtractedPrescription,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="extraction_completed",
            resource_type="extraction",
            resource_id=extraction_id,
            payload={
                "size_bytes": image.size_bytes,
                "media_type": image.media_type,
                "medication_count": len(prescription.medications),
                "warning_count": len(prescription.warnings),
                "patient_field_completeness": {
                    "name": prescription.patient.name is not None,
                    "dob": prescription.patient.dob is not None,
                    "mrn": prescription.patient.mrn is not None,
                    "phone": prescription.patient.phone is not None,
                },
                "treatment_field_completeness": {
                    "clinical_objective": prescription.treatment.clinical_objective is not None,
                },
                "medication_field_completeness": [
                    {
                        "name": medication.name is not None,
                        "dosage": medication.dosage is not None,
                        "frequency": medication.frequency is not None,
                        "duration": medication.duration is not None,
                        "objective": medication.objective is not None,
                    }
                    for medication in prescription.medications
                ],
            },
        )
    )


def _audit_failed(
    session: AsyncSession,
    *,
    extraction_id: UUID,
    error: str,
    size_bytes: int,
    declared_mime: str | None,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="extraction_failed",
            resource_type="extraction",
            resource_id=extraction_id,
            payload={
                "error": error,
                "size_bytes": size_bytes,
                "declared_mime": declared_mime,
            },
        )
    )


def _extraction_failure_code(exc: Exception) -> str:
    message = str(exc).lower()
    if "api key" in message or "openai_api_key" in message:
        return "openai_api_key_missing"
    return "extraction_failed"

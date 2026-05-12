"""POST /prescriptions/extract route behavior."""

import json
from uuid import UUID

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.extraction_schemas import ExtractedPrescription
from app.api.prescriptions import build_configured_extraction_agent, get_extraction_agent
from app.db.models import AuditLogEntry


@pytest.mark.usefixtures("postgres_container")
async def test_extract_prescription_returns_validated_draft_and_audits_without_phi(
    app_client: AsyncClient,
    db_session: AsyncSession,
    test_app,
) -> None:
    test_app.dependency_overrides[get_extraction_agent] = lambda: _agent_with_output(
        {
            "patient": {
                "name": "Eleanor Vance",
                "dob": None,
                "mrn": "RX-123",
                "phone": None,
                "confidence": {"name": 0.91, "mrn": 0.72},
            },
            "treatment": {
                "clinical_objective": "Reduce blood pressure.",
                "confidence": {"clinical_objective": 0.7},
            },
            "medications": [
                {
                    "name": "Lisinopril",
                    "dosage": "10 mg",
                    "frequency": "once daily",
                    "duration": None,
                    "objective": None,
                    "confidence": {"name": 0.95, "dosage": 0.9, "frequency": 0.8},
                }
            ],
            "warnings": ["duration not visible"],
        }
    )

    response = await app_client.post(
        "/prescriptions/extract",
        files={"file": ("script.png", b"\x89PNG\r\n\x1a\nfake-body", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["patient"]["name"] == "Eleanor Vance"
    assert body["medications"][0]["name"] == "Lisinopril"
    assert body["warnings"] == ["duration not visible"]

    audits = (
        await db_session.execute(
            select(AuditLogEntry)
            .where(AuditLogEntry.resource_type == "extraction")
            .order_by(AuditLogEntry.created_at)
        )
    ).scalars().all()

    assert [audit.event_type for audit in audits] == [
        "extraction_started",
        "extraction_completed",
    ]
    assert UUID(str(audits[0].resource_id)) == audits[1].resource_id
    completed_payload = audits[1].payload
    assert completed_payload["media_type"] == "image/png"
    assert completed_payload["size_bytes"] == len(b"\x89PNG\r\n\x1a\nfake-body")
    assert completed_payload["medication_count"] == 1
    assert completed_payload["warning_count"] == 1
    assert completed_payload["patient_field_completeness"] == {
        "name": True,
        "dob": False,
        "mrn": True,
        "phone": False,
    }
    serialised_payloads = json.dumps([audit.payload for audit in audits])
    assert "Eleanor" not in serialised_payloads
    assert "Vance" not in serialised_payloads
    assert "RX-123" not in serialised_payloads
    assert "Lisinopril" not in serialised_payloads
    assert "10 mg" not in serialised_payloads
    assert "Reduce blood pressure" not in serialised_payloads


@pytest.mark.usefixtures("postgres_container")
async def test_extract_prescription_rejects_invalid_upload_and_audits_failure(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await app_client.post(
        "/prescriptions/extract",
        files={"file": ("script.png", b"not an image", "image/png")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {"error": "unsupported_image_type"}

    audit = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.event_type == "extraction_failed")
        )
    ).scalar_one()

    assert audit.resource_type == "extraction"
    assert audit.payload["error"] == "unsupported_image_type"
    assert audit.payload["declared_mime"] == "image/png"
    assert audit.payload["size_bytes"] == len(b"not an image")


def _agent_with_output(output: dict[str, object]) -> Agent[None, ExtractedPrescription]:
    def model_function(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[ToolCallPart(output_tool.name, output)],
            model_name="extract-route-test",
        )

    return Agent(
        FunctionModel(model_function),
        output_type=ExtractedPrescription,
        defer_model_check=True,
    )


def test_build_configured_extraction_agent_uses_app_prefixed_openai_key() -> None:
    agent = build_configured_extraction_agent(SecretStr("test-openai-key"))

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert isinstance(agent.model.provider, OpenAIProvider)

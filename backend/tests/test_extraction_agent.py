"""Prescription vision extraction agent behavior."""

import json

import pytest
import structlog
from pydantic_ai import Agent
from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.extraction import build_extraction_agent, extract_prescription_image
from app.agents.extraction_schemas import ExtractedPrescription
from app.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def test_build_extraction_agent_defaults_to_vision_model() -> None:
    agent = build_extraction_agent()

    assert agent.model == "openai:gpt-5.4-mini"


async def test_extract_prescription_image_uses_prompt_and_binary_image() -> None:
    seen: dict[str, object] = {}

    def model_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["instructions"] = info.instructions or ""
        seen["prompt"] = _user_prompt_content(messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "patient": {
                            "name": "Ada Lovelace",
                            "dob": None,
                            "mrn": None,
                            "phone": None,
                            "confidence": {"name": 0.91},
                        },
                        "treatment": {
                            "clinical_objective": None,
                            "confidence": {},
                        },
                        "medications": [
                            {
                                "name": "Lisinopril",
                                "dosage": "10 mg",
                                "frequency": "once daily",
                                "duration": None,
                                "objective": None,
                                "confidence": {
                                    "name": 0.95,
                                    "dosage": 0.9,
                                    "frequency": 0.78,
                                },
                            }
                        ],
                        "warnings": ["duration not visible"],
                    },
                )
            ],
            model_name="vision-extraction-test",
        )

    agent: Agent[None, ExtractedPrescription] = build_extraction_agent(
        model=FunctionModel(model_function)
    )

    prescription = await extract_prescription_image(
        b"\x89PNG\r\n",
        "image/png",
        agent=agent,
    )

    assert prescription.patient.name == "Ada Lovelace"
    assert prescription.medications[0].name == "Lisinopril"
    assert "extract only visible prescription content" in str(seen["instructions"]).lower()
    prompt = seen["prompt"]
    assert isinstance(prompt, list)
    assert prompt[0] == "Extract the prescription image into the validated schema."
    assert isinstance(prompt[1], BinaryContent)
    assert prompt[1].data == b"\x89PNG\r\n"
    assert prompt[1].media_type == "image/png"


async def test_extract_prescription_image_logs_non_phi_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")

    def model_function(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "patient": {
                            "name": "Ada Lovelace",
                            "dob": None,
                            "mrn": None,
                            "phone": None,
                            "confidence": {"name": 0.91},
                        },
                        "treatment": {"clinical_objective": None, "confidence": {}},
                        "medications": [
                            {
                                "name": "Lisinopril",
                                "dosage": "10 mg",
                                "frequency": None,
                                "duration": None,
                                "objective": None,
                                "confidence": {"name": 0.95, "dosage": 0.9},
                            }
                        ],
                        "warnings": ["frequency not visible"],
                    },
                )
            ],
            model_name="vision-extraction-test",
        )

    agent: Agent[None, ExtractedPrescription] = build_extraction_agent(
        model=FunctionModel(model_function)
    )

    await extract_prescription_image(b"fake-image", "image/jpeg", agent=agent)

    records = _records_with_event(capsys.readouterr().out, "prescription_extracted")

    assert records
    assert records[-1]["media_type"] == "image/jpeg"
    assert records[-1]["size_bytes"] == 10
    assert records[-1]["medication_count"] == 1
    assert records[-1]["warning_count"] == 1
    assert records[-1]["patient_field_completeness"] == {
        "name": True,
        "dob": False,
        "mrn": False,
        "phone": False,
    }
    assert "Ada Lovelace" not in json.dumps(records[-1])
    assert "Lisinopril" not in json.dumps(records[-1])


def _user_prompt_content(messages: list[ModelMessage]) -> object:
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart):
                    return part.content
    raise AssertionError("user prompt not found")


def _records_with_event(captured: str, event: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in captured.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") == event:
            records.append(record)
    return records

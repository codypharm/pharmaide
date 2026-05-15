"""Model-backed placeholder providers for safety checks."""

from uuid import UUID

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.agents.model_safety_providers import (
    ModelGuardProvider,
    ModelRefereeProvider,
    build_guard_agent,
    build_referee_agent,
)
from app.agents.safety_schemas import GuardRequest, GuardResult, RefereeRequest, RefereeResult

TREATMENT_ID = UUID("11111111-1111-1111-1111-111111111111")


def test_build_guard_agent_defaults_to_high_accuracy_model() -> None:
    agent = build_guard_agent()

    assert agent.model == "openai:gpt-5"


async def test_model_guard_provider_returns_validated_payload() -> None:
    agent = build_guard_agent(
        model=TestModel(
            custom_output_args={
                "stage": "input",
                "action": "allow",
                "categories": [],
                "rationale": "Medication adherence question.",
                "confidence": 0.86,
                "safe_response": None,
                "requires_pharmacist_review": False,
            }
        )
    )
    provider = ModelGuardProvider(agent)

    payload = await provider.check(
        GuardRequest(
            stage="input",
            treatment_id=TREATMENT_ID,
            actor_role="patient",
            content="Can I take this after food?",
        )
    )

    result = GuardResult.model_validate(payload)
    assert result.stage == "input"
    assert result.action == "allow"
    assert result.confidence == 0.86


async def test_model_guard_prompt_keeps_guard_scope_and_privacy() -> None:
    seen: dict[str, str] = {}

    def model_function(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["instructions"] = info.instructions or ""
        seen["prompt"] = _user_prompt(_messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "stage": "output",
                        "action": "block",
                        "categories": ["unsafe_medical_advice"],
                        "rationale": "Unsafe medical advice detected.",
                        "confidence": 0.91,
                        "safe_response": None,
                        "requires_pharmacist_review": True,
                    },
                )
            ],
            model_name="guard-test",
        )

    agent: Agent[None, GuardResult] = build_guard_agent(model=FunctionModel(model_function))
    provider = ModelGuardProvider(agent)

    await provider.check(
        GuardRequest(
            stage="output",
            treatment_id=TREATMENT_ID,
            actor_role="assistant",
            content="Take twice as much medicine tonight.",
        )
    )

    assert "conversation and policy safety" in seen["instructions"].lower()
    assert "do not judge prescription faithfulness" in seen["instructions"].lower()
    assert "do not quote patient content" in seen["instructions"].lower()
    assert "stage: output" in seen["prompt"]
    assert "Take twice as much medicine tonight." in seen["prompt"]


async def test_model_referee_provider_returns_validated_payload() -> None:
    agent = build_referee_agent(
        model=TestModel(
            custom_output_args={
                "action": "block",
                "violations": [
                    {
                        "violation_type": "dosage_change",
                        "description": "Draft changes the approved dose.",
                    }
                ],
                "rationale": "Draft changes treatment instructions.",
                "confidence": 0.93,
                "safe_response": None,
                "requires_pharmacist_review": True,
            }
        )
    )
    provider = ModelRefereeProvider(agent)

    payload = await provider.review(
        RefereeRequest(
            treatment_id=TREATMENT_ID,
            patient_message="Can I take more?",
            assistant_draft="Take two tablets tonight.",
            prescription_context="Lisinopril 10 mg once daily.",
        )
    )

    result = RefereeResult.model_validate(payload)
    assert result.action == "block"
    assert result.violations[0].violation_type == "dosage_change"
    assert result.requires_pharmacist_review is True


async def test_model_referee_prompt_focuses_on_prescription_faithfulness() -> None:
    seen: dict[str, str] = {}

    def model_function(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["instructions"] = info.instructions or ""
        seen["prompt"] = _user_prompt(_messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "action": "block",
                        "violations": [
                            {
                                "violation_type": "prescription_mismatch",
                                "description": "Draft conflicts with treatment context.",
                            }
                        ],
                        "rationale": "Draft conflicts with treatment context.",
                        "confidence": 0.9,
                        "safe_response": None,
                        "requires_pharmacist_review": True,
                    },
                )
            ],
            model_name="referee-test",
        )

    agent: Agent[None, RefereeResult] = build_referee_agent(
        model=FunctionModel(model_function)
    )
    provider = ModelRefereeProvider(agent)

    await provider.review(
        RefereeRequest(
            treatment_id=TREATMENT_ID,
            patient_message="Can I stop this medication?",
            assistant_draft="Stop taking it tomorrow.",
            prescription_context="Metformin 500 mg twice daily.",
        )
    )

    assert "agentdog-style clinical referee" in seen["instructions"].lower()
    assert "diagnosis or dosage change" in seen["instructions"].lower()
    assert "do not quote patient content" in seen["instructions"].lower()
    assert "assistant_draft:" in seen["prompt"]
    assert "prescription_context:" in seen["prompt"]


def _user_prompt(messages: list[ModelMessage]) -> str:
    prompts: list[str] = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, UserPromptPart):
                prompts.append(str(part.content))
    return "\n".join(prompts)

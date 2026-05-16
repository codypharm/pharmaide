"""Typed patient-reply intent classifier behavior."""

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.patient_reply_classifier import (
    PatientReplyClassification,
    build_patient_reply_classifier_agent,
    classify_patient_reply_with_agent,
)


def test_build_patient_reply_classifier_agent_defaults_to_fast_classifier_model() -> None:
    agent = build_patient_reply_classifier_agent()

    assert agent.model == "openai:gpt-5-nano"


async def test_classify_patient_reply_with_agent_returns_validated_intent() -> None:
    seen: dict[str, str] = {}

    def model_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["instructions"] = info.instructions or ""
        seen["prompt"] = _user_prompt(messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "intent": "taken",
                        "confidence": 0.88,
                    },
                )
            ],
            model_name="patient-reply-classifier-test",
        )

    agent: Agent[None, PatientReplyClassification] = build_patient_reply_classifier_agent(
        model=FunctionModel(model_function)
    )

    classification = await classify_patient_reply_with_agent("All sorted now", agent=agent)

    assert classification.intent == "taken"
    assert classification.confidence == 0.88
    assert "classify one patient whatsapp message" in seen["instructions"].lower()
    assert "do not draft a reply" in seen["instructions"].lower()
    assert "All sorted now" in seen["prompt"]


def _user_prompt(messages: list[ModelMessage]) -> str:
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    raise AssertionError("expected a user prompt")
